export const API=import.meta.env.VITE_API_URL||'http://localhost:8000/api/v1';
export async function get<T>(path:string):Promise<T>{const r=await fetch(`${API}${path}`);if(!r.ok)throw new Error(`API error ${r.status}`);return r.json();}
