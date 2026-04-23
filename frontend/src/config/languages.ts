import api from './api';

export interface Runtime {
  name: string;
  display_name: string;
  file_extension: string;
  supports_packages: boolean;
  package_manager: string | null;
}

export interface LanguagesResponse {
  languages: string[];
  runtimes: Runtime[];
}

// Map backend runtime name -> Monaco editor language id
const MONACO_LANGUAGE_MAP: Record<string, string> = {
  python: 'python',
  node: 'javascript',
  ruby: 'ruby',
  bash: 'shell',
  go: 'go',
};

export const monacoLanguageFor = (runtime: string): string =>
  MONACO_LANGUAGE_MAP[runtime] || 'plaintext';

export const fetchRuntimes = async (): Promise<Runtime[]> => {
  const response = await api.get<LanguagesResponse>('/languages');
  return response.data.runtimes || [];
};

// Compact human-readable relative time for ISO timestamps. Kept small to
// avoid pulling in a date library (date-fns is not in the project).
export const formatRelativeTime = (iso: string | null | undefined): string => {
  if (!iso) return '-';
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso || '-';
  const diffSeconds = Math.round((Date.now() - then) / 1000);
  const abs = Math.abs(diffSeconds);
  const suffix = diffSeconds >= 0 ? 'ago' : 'from now';

  if (abs < 5) return 'just now';
  if (abs < 60) return `${abs} second${abs === 1 ? '' : 's'} ${suffix}`;
  const minutes = Math.round(abs / 60);
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? '' : 's'} ${suffix}`;
  const hours = Math.round(abs / 3600);
  if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ${suffix}`;
  const days = Math.round(abs / 86400);
  if (days < 30) return `${days} day${days === 1 ? '' : 's'} ${suffix}`;
  const months = Math.round(abs / (86400 * 30));
  if (months < 12) return `${months} month${months === 1 ? '' : 's'} ${suffix}`;
  const years = Math.round(abs / (86400 * 365));
  return `${years} year${years === 1 ? '' : 's'} ${suffix}`;
};
