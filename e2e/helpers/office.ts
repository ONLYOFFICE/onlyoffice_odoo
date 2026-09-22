// Copyright (C) 2026 Ascensio System SIA
import JSZip from "jszip"

/** Plain text of a docx/xlsx/pptx file: every XML part with the tags stripped. */
export async function officeText(file: Buffer): Promise<string> {
  const zip = await JSZip.loadAsync(file)
  const parts = Object.keys(zip.files).filter((name) => name.endsWith(".xml"))
  const xml = await Promise.all(parts.map((name) => zip.file(name)!.async("string")))
  return xml.join("\n").replace(/<[^>]+>/g, "")
}
