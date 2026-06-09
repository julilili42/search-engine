#[derive(Debug)]
pub struct Tokenizer<'a> {
    pub content: &'a [char],
}

impl<'a> Tokenizer<'a> {
    pub fn new(content: &'a [char]) -> Self {
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

pub fn tokenize(text: &str) -> Vec<String> {
    let chars = text.chars().collect::<Vec<_>>();

    Tokenizer::new(&chars)
        .filter(|term| term.len() >= 2)
        .collect()
}
