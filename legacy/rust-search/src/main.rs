use clap::Parser;
use std::io;

use crate::{
    cli::{Cli, Commands},
    indexer::index,
    search::search,
};

mod cli;
mod html;
mod indexer;
mod search;
mod tokenizer;

fn main() -> io::Result<()> {
    let cli = Cli::parse();

    match cli.command {
        Commands::Index { dir, output } => index(&dir, &output)?,
        Commands::Search {
            index,
            query,
            top_n,
        } => {
            let _ = search(&index, &query, top_n)?;
        }
    }
    Ok(())
}
