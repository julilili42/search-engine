use std::{fs, io, path::Path};

use scraper::{Html, Selector};

pub fn parse_html_selectors() -> Selector {
    Selector::parse(
        "body h1, body h2, body h3, body h4, \
     body p, body li, body td, body th, \
     body figcaption, body blockquote",
    )
    .expect("TODO")
}

// crawler might have saved other file extensions, only use html
pub fn is_html_file(entry: &fs::DirEntry) -> bool {
    if !entry.file_type().expect("TODO").is_file() {
        return false;
    }

    entry
        .path()
        .extension()
        .and_then(|ext| ext.to_str())
        .is_some_and(|ext| ext.eq_ignore_ascii_case("html"))
}

pub fn extract_text_from_html(file_path: &Path, selector: &Selector) -> io::Result<String> {
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
