use clap::{Parser, Subcommand};
use scraper::{Html, Selector};
use std::{
    collections::HashMap,
    fs::{self, File},
    io,
    path::{Path, PathBuf},
};
use tiny_http::{Header, Response, Server};

#[derive(Parser, Debug)]
#[command(name = "tuebingen-search")]
#[command(version, about = "Small search engine for TÜpedia HTML files")]
struct Cli {
    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand, Debug)]

enum Commands {
    Index {
        #[arg(short, long, default_value = "../data/tuepedia/html")]
        dir: String,

        #[arg(short, long, default_value = "index.json")]
        output: String,
    },
    Search {
        #[arg(short, long, default_value = "index.json")]
        index: String,
        #[arg(short, long)]
        query: String,
        #[arg(short, long, default_value_t = 10)]
        n_th: usize,
    },
    Serve {
        #[arg(short, long, default_value = "localhost:8000")]
        adress: String,
    },
}

#[derive(Debug)]
struct Tokenizer<'a> {
    content: &'a [char],
}

impl<'a> Tokenizer<'a> {
    fn new(content: &'a [char]) -> Self {
        Self { content }
    }

    fn trim_left(&mut self) {
        while !self.content.is_empty() && self.content[0].is_whitespace() {
            // moves window
            self.content = &self.content[1..]
        }
    }

    fn chop(&mut self, i: usize) -> &'a [char] {
        let token = &self.content[..i];
        self.content = &self.content[i..];
        token
    }

    fn chop_while<P>(&mut self, mut predicate: P) -> &'a [char]
    where
        P: FnMut(&char) -> bool,
    {
        let mut i = 0;

        while i < self.content.len() && predicate(&self.content[i]) {
            i += 1;
        }
        return self.chop(i);
    }

    fn next_token(&mut self) -> Option<String> {
        loop {
            self.trim_left();

            if self.content.is_empty() {
                return None;
            }

            if self.content[0].is_numeric() {
                let token = self.chop_while(|x| x.is_numeric());
                return Some(token.iter().collect::<String>().to_lowercase());
            }

            if self.content[0].is_alphabetic() {
                let token = self.chop_while(|x| x.is_alphanumeric());
                return Some(token.iter().collect::<String>().to_lowercase());
            }

            // ignore punctuation
            self.chop(1);
            continue;
        }
    }
}

impl<'a> Iterator for Tokenizer<'a> {
    type Item = String;

    fn next(&mut self) -> Option<Self::Item> {
        self.next_token()
    }
}

fn extract_text_from_html(file_path: &Path, selector: &Selector) -> io::Result<String> {
    let html = fs::read_to_string(file_path)?;
    let document = Html::parse_document(&html);
    let mut text = String::new();

    for element in document.select(selector) {
        let raw_text = element.text().collect::<Vec<_>>().join(" ");
        let clean_text = raw_text.split_whitespace().collect::<Vec<_>>().join(" ");
        text.push_str(&clean_text);
        text.push(' ');
    }

    return Ok(text);
}
fn main() -> io::Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Index { dir, output } => index(&dir, &output),
        Commands::Search { index, query, n_th } => search(&index, &query, n_th),
        Commands::Serve { adress } => {
            let server = Server::http(&adress).expect("TODO");

            println!("listening at http://{adress}/ ...");

            for request in server.incoming_requests() {
                println!(
                    "received request! method: {:?}, url: {:?}",
                    request.method(),
                    request.url(),
                );

                let response = Response::from_string(
                    r#"
                <html>
                <head>
                <title>Test</title>
                </head>
                <body>
                <h1>Test</h1>
                </body>
                </html>
                "#,
                )
                .with_header(
                    Header::from_bytes("Content-Type", "text/html; charset=utf-8").expect("TODO"),
                );
                request.respond(response).expect("TODO");
            }

            Ok(())
        }
    }
}

fn tokenize(text: &str) -> Vec<String> {
    let chars = text.chars().collect::<Vec<_>>();

    Tokenizer::new(&chars)
        .filter(|term| term.len() >= 2)
        .collect()
}

fn search(index_path: &str, query: &str, n_th: usize) -> io::Result<()> {
    let index_file = File::open(index_path)?;
    println!("Reading {index_path} index file");
    let search_index: SearchIndex = serde_json::from_reader(index_file).expect("TODO");

    let term_freq_index = search_index.term_frequency_index;
    let inverse_document_index = search_index.inverse_document_index;

    println!(
        "{index_path} contains {count_files}",
        count_files = term_freq_index.len()
    );

    let mut query_terms = tokenize(query);
    query_terms.sort();
    query_terms.dedup();

    if query_terms.is_empty() {
        eprintln!("No searchable query terms in query.");
        return Ok(());
    }

    println!("Searching for {query_terms:?} ...");

    let mut result = term_freq_index
        .iter()
        .map(|(path, term_frequency)| {
            let score: f64 = query_terms
                .iter()
                .map(|term| {
                    // retrieves frequency of for each query term in document 
                    let tf = term_frequency.get(term).copied().unwrap_or(0) as f64;
                    let idf = inverse_document_index.get(term).copied().unwrap_or(0.0);

                    tf * idf
                })
                .sum();

            (path, score)
        })
        .filter(|(_, score)| *score > 0.0)
        .collect::<Vec<_>>();

    result.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());

    for (path, score) in result.iter().take(n_th) {
        println!("{score:>8.3} {}", path.display());
    }

    Ok(())
}

type TermFreq = HashMap<String, usize>;
type TermFreqIndex = HashMap<PathBuf, TermFreq>;
type InverseDocumentIndex = HashMap<String, f64>;

#[derive(Debug, serde::Serialize, serde::Deserialize)]
struct SearchIndex {
    term_frequency_index: TermFreqIndex,
    inverse_document_index: InverseDocumentIndex,
}


fn compute_idf(index: &TermFreqIndex) -> InverseDocumentIndex {
    let n = index.len();
    let mut document_frequency: HashMap<String, usize> = HashMap::new();

    for term_frequency in index.values() {
        for term in term_frequency.keys() {
            *document_frequency.entry(term.clone()).or_insert(0) += 1
        }
    }

    document_frequency
        .into_iter()
        .map(|(term, df)| {
            let idf = ((1.0 + n as f64) / (1.0 + df as f64)).ln() + 1.0;
            (term, idf)
        })
        .collect()
}

fn index(dir_path: &str, index_path: &str) -> io::Result<()> {
    let dir = fs::read_dir(dir_path)?;

    let mut term_frequency_index = TermFreqIndex::new();

    let selector = Selector::parse(
        "body h1, body h2, body h3, body h4, \
     body p, body li, body td, body th, \
     body figcaption, body blockquote",
    )
    .unwrap();

    for file in dir {
        let file = file?;
        let file_type = file.file_type()?;
        let file_path = file.path();
        let file_extension = file_path
            .extension()
            .and_then(|ext| ext.to_str())
            .map(|ext| ext.eq_ignore_ascii_case("html"))
            .unwrap_or(false);

        if !file_type.is_file() {
            eprintln!("Skipped non-file {file:?}", file = file.path());
            continue;
        }

        // crawler might have saved other file extensions, only use html
        if !file_extension {
            eprintln!("Skipped non-html file {file:?}", file = file.path());
            continue;
        }

        println!("Indexing {file_path:?}");

        let text = extract_text_from_html(&file_path, &selector)?;
        let terms = tokenize(&text);

        let mut term_frequency = TermFreq::new();

        for term in terms {
            *term_frequency.entry(term).or_insert(0) += 1;
        }

        term_frequency_index.insert(file_path, term_frequency);
    }

    let inverse_document_index: InverseDocumentIndex = compute_idf(&term_frequency_index);

    for (path, tf) in &term_frequency_index {
        println!("{path:?} has {count} unique tokens", count = tf.len())
    }

    let search_index = SearchIndex {
        term_frequency_index,
        inverse_document_index
    };

    println!("Saving {index_path} ...");
    let index_file = File::create(index_path)?;
    serde_json::to_writer(index_file, &search_index).expect("TODO");

    Ok(())
}
