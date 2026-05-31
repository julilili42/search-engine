use scraper::{Html, Selector};
use std::{collections::HashMap, fs, io};

fn index_document(_content: &str) -> HashMap<String, usize> {
    todo!("TODO")
}


fn extract_text_from_html(file_path: &str) -> io::Result<String> {
    let html = fs::read_to_string(file_path)?;
    let document = Html::parse_document(&html);

    let selector = Selector::parse("body h1, body h2, body h3, body h4, \
     body p, body li, body td, body th, \
     body figcaption, body blockquote"
    ).unwrap();


    let mut text = String::new();
    for element in document.select(&selector) {
        let raw_text = element.text().collect::<Vec<_>>().join(" ");
        let clean_text = raw_text.split_whitespace().collect::<Vec<_>>().join(" ");
        text.push_str(&clean_text);
    }

    return Ok(text)
}


fn main() -> io::Result<()> {
    let all_documents = HashMap::<String, HashMap<String, usize>>::new();
    
    let dir_path = "../data/tuepedia/html";
    let dir = fs::read_dir(dir_path)?;

    for file in dir {
        let file_path = file?.path();
        let content = extract_text_from_html(file_path.to_str().expect("TODO"))?;   
        println!("{file_path:?} => {size}", size=content.len());
    }


    //println!("{html:?}", html=extract_text_from_html("../data/tuepedia/html/00023754-andachtsraum-hno-und-augenklinik.html").unwrap());
    Ok(())
}
