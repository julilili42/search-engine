use std::{
    collections::HashMap,
    fs::File,
    io::{self, BufReader},
    time::Instant,
};

use crate::{indexer::SearchIndex, tokenizer::tokenize};

pub fn search(index_path: &str, query: &str, top_n: usize) -> io::Result<()> {
    let start = Instant::now();

    let index_file = File::open(index_path)?;
    println!("INFO: Opened file after {:?}", start.elapsed());

    let load_start = Instant::now();
    let reader = BufReader::new(index_file);
    println!("INFO: Reading {index_path} inverted index.");

    let search_index: SearchIndex = bincode::deserialize_from(reader).expect("TODO");
    println!("INFO: Loaded index after {:?}", load_start.elapsed());
    println!(
        "INFO: {index_path} contains {count_documents} documents.",
        count_documents = search_index.documents.len()
    );

    let search_start = Instant::now();
    // prepare query
    let mut query_terms = tokenize(query);
    query_terms.sort();
    query_terms.dedup();

    if query_terms.is_empty() {
        eprintln!("ERROR: No searchable query terms in query.");
        return Ok(());
    }

    println!(
        "INFO: Searching for {query_terms:?} ...",
        query_terms = query_terms.join(" ")
    );

    let mut scores: HashMap<u32, f32> = HashMap::new();

    for term in query_terms {
        if let Some(postings) = search_index.inverted_index.get(&term) {
            for posting in postings {
                *scores.entry(posting.doc_index.clone()).or_insert(0.0) += posting.score;
            }
        }
    }

    let mut results = scores.into_iter().collect::<Vec<_>>();
    results.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));

    for (doc_index, score) in results.iter().take(top_n) {
        let document = &search_index.documents[*doc_index as usize];
        println!(
            "{score:>8.3} {} {} terms",
            document.path.display(),
            document.length
        );
    }

    println!("INFO: Search computation took {:?}", search_start.elapsed());
    Ok(())
}
