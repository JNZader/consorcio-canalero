#!/usr/bin/env node
/**
 * One-shot: parse tramites-consorcio/index.html dataset → catalog.py source.
 * Run from laptop; output is metadata only (no file bytes).
 */
import fs from "node:fs";
import path from "node:path";

const INDEX =
  process.env.TRAMITES_INDEX ||
  "/home/javier/programacion/tramites-consorcio/index.html";
const OUT =
  process.argv[2] ||
  path.resolve(
    "gee-backend/app/domains/documentos/catalog.py",
  );

const html = fs.readFileSync(INDEX, "utf8");
const marker = "const dataset = ";
const start = html.indexOf(marker);
if (start < 0) throw new Error("dataset marker not found");
let i = start + marker.length;
while (html[i] && /\s/.test(html[i])) i++;
if (html[i] !== "[") throw new Error("expected array");
let depth = 0;
let end = -1;
for (let j = i; j < html.length; j++) {
  const c = html[j];
  if (c === "[") depth++;
  else if (c === "]") {
    depth--;
    if (depth === 0) {
      end = j + 1;
      break;
    }
  }
}
if (end < 0) throw new Error("unclosed dataset");
const dataset = JSON.parse(html.slice(i, end));

const MIME = {
  ".pdf": "application/pdf",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".tex": "application/x-tex",
  ".html": "text/html",
  ".htm": "text/html",
  ".kmz": "application/vnd.google-earth.kmz",
  ".kml": "application/vnd.google-earth.kml+xml",
  ".docx":
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  ".doc": "application/msword",
  ".md": "text/markdown",
};

function slugify(name) {
  return name
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 80) || "file";
}

function mimeFor(rel) {
  const ext = path.extname(rel).toLowerCase();
  return MIME[ext] || "application/octet-stream";
}

function isPreview(rel) {
  return rel.includes("visor_assets/previews/");
}

function collectUrls(entry) {
  const urls = [];
  for (const a of entry.attachments || []) {
    if (a?.url) urls.push({ nombre: a.name || path.basename(a.url), url: a.url });
  }
  for (const p of entry.pdfDocuments || []) {
    if (p?.url) urls.push({ nombre: p.name || path.basename(p.url), url: p.url });
  }
  for (const l of entry.latexDocs || []) {
    if (l?.pdf) urls.push({ nombre: l.label || path.basename(l.pdf), url: l.pdf });
  }
  return urls;
}

const dossiers = [];
for (const entry of dataset) {
  const seen = new Set();
  const files = [];
  for (const { nombre, url } of collectUrls(entry)) {
    const rel = url.replace(/^\.\//, "");
    if (!rel || isPreview(rel)) continue;
    if (seen.has(rel)) continue;
    seen.add(rel);
    const base = path.basename(rel);
    const fileId = `${entry.id}__${slugify(base)}`;
    files.push({
      id: fileId,
      nombre: base,
      mime: mimeFor(rel),
      relative_path: rel,
      display_name: nombre,
    });
  }
  dossiers.push({
    id: entry.id,
    titulo: entry.title,
    group: entry.group,
    group_label: entry.groupLabel || null,
    expediente: entry.expediente || "",
    badge: entry.badge || null,
    fecha: entry.fecha || null,
    clasificacion: "privado",
    destinatario: entry.organismo || null,
    autores: null,
    files,
  });
}

function pyStr(s) {
  if (s === null || s === undefined) return "None";
  return JSON.stringify(s);
}

const lines = [];
lines.push('"""Code-defined Documentos catalog (Wave 1). Metadata only — no bytes."""');
lines.push("");
lines.push("from __future__ import annotations");
lines.push("");
lines.push("from dataclasses import dataclass");
lines.push("from typing import Literal");
lines.push("");
lines.push("");
lines.push("@dataclass(frozen=True, slots=True)");
lines.push("class ArchivoCatalogo:");
lines.push("    id: str");
lines.push("    nombre: str");
lines.push("    mime: str");
lines.push("    relative_path: str");
lines.push("    display_name: str | None = None");
lines.push("    bytes: int | None = None");
lines.push("");
lines.push("");
lines.push("@dataclass(frozen=True, slots=True)");
lines.push("class DocumentoCatalogo:");
lines.push("    id: str");
lines.push("    titulo: str");
lines.push("    group: str");
lines.push("    expediente: str");
lines.push('    clasificacion: Literal["privado"]');
lines.push("    files: tuple[ArchivoCatalogo, ...]");
lines.push("    group_label: str | None = None");
lines.push("    badge: str | None = None");
lines.push("    fecha: str | None = None");
lines.push("    destinatario: str | None = None");
lines.push("    autores: tuple[str, ...] | None = None");
lines.push("");
lines.push("");
lines.push("DOCUMENTOS: tuple[DocumentoCatalogo, ...] = (");

for (const d of dossiers) {
  lines.push("    DocumentoCatalogo(");
  lines.push(`        id=${pyStr(d.id)},`);
  lines.push(`        titulo=${pyStr(d.titulo)},`);
  lines.push(`        group=${pyStr(d.group)},`);
  lines.push(`        expediente=${pyStr(d.expediente)},`);
  lines.push('        clasificacion="privado",');
  lines.push(`        group_label=${pyStr(d.group_label)},`);
  lines.push(`        badge=${pyStr(d.badge)},`);
  lines.push(`        fecha=${pyStr(d.fecha)},`);
  lines.push(`        destinatario=${pyStr(d.destinatario)},`);
  lines.push("        files=(");
  for (const f of d.files) {
    lines.push("            ArchivoCatalogo(");
    lines.push(`                id=${pyStr(f.id)},`);
    lines.push(`                nombre=${pyStr(f.nombre)},`);
    lines.push(`                mime=${pyStr(f.mime)},`);
    lines.push(`                relative_path=${pyStr(f.relative_path)},`);
    lines.push(`                display_name=${pyStr(f.display_name)},`);
    lines.push("            ),");
  }
  lines.push("        ),");
  lines.push("    ),");
}
lines.push(")");
lines.push("");
lines.push("");
lines.push("_BY_ID: dict[str, DocumentoCatalogo] = {d.id: d for d in DOCUMENTOS}");
lines.push("");
lines.push("");
lines.push("def list_documentos(group: str | None = None) -> tuple[DocumentoCatalogo, ...]:");
lines.push('    """Return catalog rows, optionally filtered by exact group key."""');
lines.push("    if group is None:");
lines.push("        return DOCUMENTOS");
lines.push("    return tuple(d for d in DOCUMENTOS if d.group == group)");
lines.push("");
lines.push("");
lines.push("def get_documento(dossier_id: str) -> DocumentoCatalogo | None:");
lines.push("    return _BY_ID.get(dossier_id)");
lines.push("");
lines.push("");
lines.push(
  "def get_archivo(dossier_id: str, file_id: str) -> tuple[DocumentoCatalogo, ArchivoCatalogo] | None:",
);
lines.push("    doc = _BY_ID.get(dossier_id)");
lines.push("    if doc is None:");
lines.push("        return None");
lines.push("    for archivo in doc.files:");
lines.push("        if archivo.id == file_id:");
lines.push("            return doc, archivo");
lines.push("    return None");
lines.push("");

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, lines.join("\n"));
console.log(
  `wrote ${OUT}: ${dossiers.length} dossiers, ${dossiers.reduce((n, d) => n + d.files.length, 0)} files`,
);
const groups = {};
for (const d of dossiers) groups[d.group] = (groups[d.group] || 0) + 1;
console.log("groups", groups);
