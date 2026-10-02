export interface Document {
  id: string;
  name: string;
  source: string;
  mime: string;
  size: number;
  created_at: string;
  chunk_count: number;
  embedding_model: string;
}
export interface Source {
  id: string;
  document_id: string;
  name: string;
  source: string;
  page: number | null;
  text: string;
  score: number;
  rank_score: number;
  citation: number;
}
export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources: Source[];
  status: "complete" | "interrupted" | "error";
  created_at?: string;
}
export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: Message[];
}
export interface Status {
  connected: boolean;
  llm_ready: boolean;
  embedding_ready: boolean;
  llm_model: string;
  embedding_model: string;
  max_upload_mb: number;
}
export interface Preferences {
  top_k: number;
  min_score: number;
  temperature: number;
}
