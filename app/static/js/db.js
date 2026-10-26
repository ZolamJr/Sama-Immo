// IndexedDB : cache des lectures (hors ligne) + file d'attente des actions (F10).
const DB_NOM = "samaimmo";
const DB_VERSION = 1;
let _db = null;

export function db() {
  if (_db) return Promise.resolve(_db);
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NOM, DB_VERSION);
    req.onupgradeneeded = (e) => {
      const base = e.target.result;
      if (!base.objectStoreNames.contains("cache")) base.createObjectStore("cache");
      if (!base.objectStoreNames.contains("outbox")) base.createObjectStore("outbox", { keyPath: "id", autoIncrement: true });
      if (!base.objectStoreNames.contains("meta")) base.createObjectStore("meta");
    };
    req.onsuccess = () => { _db = req.result; resolve(_db); };
    req.onerror = () => reject(req.error);
  });
}

function tx(store, mode) {
  return db().then((base) => base.transaction(store, mode).objectStore(store));
}

function _demande(store, op) {
  return new Promise((resolve, reject) => {
    const r = op;
    r.onsuccess = () => resolve(r.result);
    r.onerror = () => reject(r.error);
  });
}

// ---- cache clé/valeur (réponses GET) ----
export async function cacheSet(cle, valeur) {
  try { const s = await tx("cache", "readwrite"); await _demande(s, s.put({ t: Date.now(), v: valeur }, cle)); } catch (e) { /* silencieux */ }
}
export async function cacheGet(cle) {
  try { const s = await tx("cache", "readonly"); const r = await _demande(s, s.get(cle)); return r || null; } catch (e) { return null; }
}
export async function cacheVider() {
  try { const s = await tx("cache", "readwrite"); await _demande(s, s.clear()); } catch (e) { /* silencieux */ }
}

// ---- file d'attente (outbox) ----
export async function outboxAjouter(action) {
  const s = await tx("outbox", "readwrite");
  return _demande(s, s.add({ ...action, cree_le: Date.now(), tentatives: 0 }));
}
export async function outboxListe() {
  const s = await tx("outbox", "readonly");
  return _demande(s, s.getAll());
}
export async function outboxRetirer(id) {
  const s = await tx("outbox", "readwrite");
  return _demande(s, s.delete(id));
}
export async function outboxVider() {
  const s = await tx("outbox", "readwrite");
  return _demande(s, s.clear());
}

// ---- méta (numéro provisoire, etc.) ----
export async function metaSet(cle, valeur) {
  const s = await tx("meta", "readwrite");
  return _demande(s, s.put(valeur, cle));
}
export async function metaGet(cle) {
  const s = await tx("meta", "readonly");
  return _demande(s, s.get(cle));
}

// UUID côté appareil (F10 : identifiants générés localement).
export function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

let _device_id = null;
export function deviceId() {
  if (_device_id) return _device_id;
  try { _device_id = localStorage.getItem("device_id") || ""; } catch { _device_id = ""; }
  if (!_device_id) {
    _device_id = uuid().slice(0, 8);
    try { localStorage.setItem("device_id", _device_id); } catch { /* ignoré */ }
  }
  return _device_id;
}
