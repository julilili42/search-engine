use std::{
    collections::HashMap,
    fs::{self, File},
    io::{self, BufWriter},
    path::PathBuf,
};

use crate::{
    html::{extract_text_from_html, is_html_file, parse_html_selectors},
    tokenizer::tokenize,
};

type InvertedIndex = HashMap<String, Vec<Posting>>;
type TermFrequency = HashMap<String, usize>;
type TermFrequenciesByDocument = HashMap<Document, TermFrequency>;
type InverseDocumentFrequency = HashMap<String, f32>;

#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct Posting {
    pub doc_index: u32,
    pub score: f32,
}

#[derive(Debug, serde::Serialize, serde::Deserialize, Eq, Hash, PartialEq)]
pub struct Document {
    pub path: PathBuf,
    pub length: usize,
    pub text_snippet: String,
}

#[derive(Debug, serde::Serialize, serde::Deserialize)]
pub struct SearchIndex {
    pub documents: Vec<Document>,
    pub inverted_index: InvertedIndex,
}

// computes frequency of terms
fn compute_tf(terms: Vec<String>) -> TermFrequency {
    let mut term_frequency = TermFrequency::new();

    for term in terms {
        *term_frequency.entry(term).or_insert(0) += 1;
    }

    term_frequency
}

// computes smoothed idf
fn compute_idf(index: &TermFrequenciesByDocument) -> InverseDocumentFrequency {
    let n = index.len();
    let df = compute_df(index);

    df.into_iter()
        .map(|(term, freq)| {
            let idf = ((1.0 + n as f32) / (1.0 + freq as f32)).ln() + 1.0;
            (term, idf)
        })
        .collect()
}

// number of documents which contain term
fn compute_df(index: &TermFrequenciesByDocument) -> TermFrequency {
    let mut df: HashMap<String, usize> = HashMap::new();

    for tf in index.values() {
        for term in tf.keys() {
            *df.entry(term.clone()).or_insert(0) += 1
        }
    }
    df
}

fn compute_tf_idf(frequency: usize, idf_score: f32) -> f32 {
    frequency as f32 * idf_score
}

fn build_search_index(term_freq_index: TermFrequenciesByDocument) -> SearchIndex {
    let idf = compute_idf(&term_freq_index);

    let mut documents = Vec::with_capacity(term_freq_index.len());
    let mut inverted_index = InvertedIndex::new();

    for (file_path, term_frequency) in term_freq_index {
        let doc_index = documents.len() as u32;

        documents.push(file_path);
        add_document_to_index(&mut inverted_index, doc_index, term_frequency, &idf);
    }

    SearchIndex {
        documents,
        inverted_index,
    }
}

fn add_document_to_index(
    inverted_index: &mut InvertedIndex,
    doc_index: u32,
    term_frequency: TermFrequency,
    idf: &InverseDocumentFrequency,
) {
    for (term, frequency) in term_frequency {
        let idf_score = idf.get(&term).copied().unwrap_or(0.0);
        let score = compute_tf_idf(frequency, idf_score);

        inverted_index
            .entry(term)
            .or_default()
            .push(Posting { doc_index, score });
    }
}

pub fn index(dir_path: &str, index_path: &str) -> io::Result<()> {
    let dir = fs::read_dir(dir_path)?;

    let mut term_frequency_index = TermFrequenciesByDocument::new();

    let selector = parse_html_selectors();

    for file in dir {
        let file = file?;
        let file_path = file.path();

        if !is_html_file(&file) {
            eprintln!("WARN: Skipped non-html file: {}", file_path.display());
            continue;
        }

        println!("INFO: Indexing {file_path:?}");

        let text = extract_text_from_html(&file_path, &selector)?;
        let terms = tokenize(&text);

        let snippet_length = terms.len() / 10 as usize;
        let document = Document {
            path: file_path,
            length: terms.len(),
            text_snippet: terms[..snippet_length].join(" "),
        };
        let term_frequency = compute_tf(terms);

        term_frequency_index.insert(document, term_frequency);
    }

    for (document, tf) in &term_frequency_index {
        println!(
            "INFO: {path} has {count} unique tokens",
            path = document.path.display(),
            count = tf.len()
        )
    }

    println!("INFO: Computing inverted index...");
    let search_index = build_search_index(term_frequency_index);

    println!("INFO: Saving {index_path}...");

    let index_file = File::create(index_path)?;
    let writer = BufWriter::new(index_file);

    bincode::serialize_into(writer, &search_index).expect("TODO");

    Ok(())
}
