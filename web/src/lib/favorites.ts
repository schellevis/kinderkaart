/**
 * Favorites — persisted in localStorage under key "kinderkaart:favs".
 * Stored as a JSON array of poi_id strings.
 */

const STORAGE_KEY = "kinderkaart:favs";

function load(): string[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed as string[];
    return [];
  } catch {
    return [];
  }
}

function save(ids: string[]): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(ids));
}

export class Favorites {
  list(): string[] {
    return load();
  }

  has(id: string): boolean {
    return load().includes(id);
  }

  add(id: string): void {
    const current = load();
    if (!current.includes(id)) {
      save([...current, id]);
    }
  }

  remove(id: string): void {
    save(load().filter((i) => i !== id));
  }

  replace(oldId: string, newId: string): void {
    const current = load();
    if (!current.includes(oldId)) return;
    save(Array.from(new Set(current.map((id) => (id === oldId ? newId : id)))));
  }

  toggle(id: string): boolean {
    if (this.has(id)) {
      this.remove(id);
      return false;
    } else {
      this.add(id);
      return true;
    }
  }

  clear(): void {
    save([]);
  }
}
