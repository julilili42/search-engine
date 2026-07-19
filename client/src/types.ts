export type SearchResult = {
  rank: number
  score: number
  path: string
  url: string | null
  snippet: string
  embedding_score: number | null
  embedding_x: number | null
  embedding_y: number | null
}
