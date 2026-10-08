# Project briefs, files and links

AI Office keeps client requirements with the project. Add files when creating a project, later under **Settings**, or through **Knowledge base → Add material → Files and links**. The interface uses Russian labels: `Новый проект`, `Настройки`, `База знаний`, `ТЗ и материалы`.

## Create a project with a brief

1. Open **Settings → Create another project**.
2. Enter a recognizable name and a context: audience, required functions, expected deliverable, style and constraints. Examples appear inside the fields, and help text remains visible after typing.
3. Choose multiple files or drag them onto the file area. Add reference URLs with optional titles. A typed URL is also included when saving, without requiring a separate Add click.
4. Review the file names and sizes. Remove unwanted files or links before saving.
5. Choose **Create project**. The project receives eight starter roles, its context and the uploaded source materials.

If an individual upload fails, the dialog stays open and identifies the failed entry. **Retry adding** reuses the created project and skips successfully saved entries. Closing after a partial save explains which data is already stored; remaining local selections must be added again later. This retry state belongs to the current dialog, not a persistent offline queue. A full page reload loses unsaved selections.

The name is limited to 120 characters; context to 20,000. Each original file is limited to **50 MiB** (52,428,800 bytes). The UI calls this 50 MB. There is no total project storage quota in this local MVP; monitor disk space when storing many videos.

## What agents receive

| Material | Stored original | Content available to a text stage |
| --- | --- | --- |
| PDF with a text layer | Exact uploaded bytes | Extracted text, subject to limits |
| DOCX | Exact uploaded bytes | Paragraphs, tables, headers and footers |
| Text, Markdown, CSV, JSON and supported code files | Exact uploaded bytes | Decoded text; code is never executed |
| Image, photo, video or audio | Exact uploaded bytes | File name, type, size and an explicit reference note |
| Other binary files, including legacy DOC | Exact uploaded bytes | Metadata/reference note; no invented text |
| HTTP/HTTPS URL | URL and title | The URL and a note that its content was not fetched |

Readable documents use extraction only when the original is at most **10 MiB**. Extracted content is limited to **100,000 characters**. The material shows whether text was extracted, truncated, empty, unsupported or failed. An extraction failure preserves the original and provides a Russian explanation; it does not discard the upload.

PDF extraction reads at most 200 pages, with bounded stream decompression and an aggregate decoded-content budget. Scanned pages do not receive OCR. Password-protected PDFs are retained with a failed-extraction note. DOCX parsing bounds ZIP members, uncompressed volume and XML size, and rejects DTD/entity declarations. Text supports UTF-8, BOM-marked UTF-16/32 and Windows-1251; binary data with a text extension is rejected by the text parser.

Images and media have a browser preview when their actual format is supported; the original can always be downloaded. Preview compatibility depends on the browser and codecs. Attaching a photo or video **does not** send its binary contents to Codex or an API model, perform visual analysis, transcribe audio or create captions. Add a written description, transcript or separate text brief when a text stage needs that information. SVG, HTML and PDF originals are downloadable and are not embedded as active previews.

URLs are stored without fetching a page, downloading a remote document or bypassing a sharing permission. If the instructions exist only in a linked document, download/upload that document or paste its text.

## Add materials to an existing project

- **Settings:** edit name/context, select files or references, then choose **Save project**. Previously stored files and links appear below the editor.
- **Knowledge base:** choose **Add material**, then **Files and links**. Plain Markdown/text notes remain available under **Text**.
- Open a material to inspect the extracted text/reference note, view supported media or download the original. The existing Markdown export downloads the stored text, not the binary file.

The queue allows removing entries before upload. Deleting already stored materials is not provided by this feature. Uploading the same file name and SHA-256 bytes to the same project reuses the existing material; modified bytes or a different project create a separate entry. Links with the same URL and title are also reused.

## Permissions and privacy

New task forms list source materials with their extraction status. Select which sources the task needs. The stage receives those sources only when its member has the `project_context` capability. Materials from another project cannot be referenced. File metadata and extracted text can reach the selected model; raw bytes and local filesystem paths never enter the stage payload.

Originals live under `<OFFICE_DATA_DIR>/attachments/`, using generated material IDs instead of client filenames. SQLite holds public metadata and the extracted content. Both are local plaintext data protected by the OS account. Back up the entire data directory with the server stopped. Git and distributable ZIPs exclude project data and uploads.

Upload routes preserve the local Host/Origin guard. The one raw-binary POST route requires `application/octet-stream`; other mutations retain their JSON boundary. Downloads are scoped to the owning project and use safe filename headers with `nosniff`. Parsing runs in a separate Python process with a minimal environment, a 15-second timeout and at most two concurrent extraction processes. The subprocess is a resource-control measure, not an OS sandbox for hostile tenants. Keep this application local to its owner.

For route examples see [API.md](API.md); for checks see [TESTING.md](TESTING.md).
