import { apiClient } from "./client";

export interface HelpSource {
  id: string;
  title: string;
  module: string;
  screen?: string | null;
}

export interface HelpAskResponse {
  answer: string;
  grounded: boolean;
  sources: HelpSource[];
  module?: string | null;
  screen?: string | null;
}

export interface HelpContextEntry {
  id: string;
  type: string;
  title: string;
  answer: string;
  screen?: string | null;
}

export interface HelpContextResponse {
  module?: string | null;
  screen?: string | null;
  entries: HelpContextEntry[];
}

export const askHelp = (question: string, path?: string) =>
  apiClient.post<HelpAskResponse>("/api/help/ask", { question, path });

export const getHelpContext = (path: string) =>
  apiClient.get<HelpContextResponse>("/api/help/context", { params: { path } });
