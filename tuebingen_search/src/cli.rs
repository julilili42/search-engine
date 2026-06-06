use clap::{Parser, Subcommand};

#[derive(Parser, Debug)]
#[command(name = "tuebingen-search")]
#[command(version, about = "Small search engine for TÜpedia HTML files")]
pub struct Cli {
    #[command(subcommand)]
    pub command: Commands,
}

#[derive(Subcommand, Debug)]

pub enum Commands {
    Index {
        #[arg(short, long, default_value = "../data/tuepedia/html")]
        dir: String,

        #[arg(short, long, default_value = "index.bin")]
        output: String,
    },
    Search {
        #[arg(short, long, default_value = "index.bin")]
        index: String,
        #[arg(short, long)]
        query: String,
        #[arg(short, long, default_value_t = 10)]
        top_n: usize,
    },
}
