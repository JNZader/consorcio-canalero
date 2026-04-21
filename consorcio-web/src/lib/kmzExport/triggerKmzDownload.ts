/**
 * triggerKmzDownload
 *
 * Phase 4 download trigger for the `kmz-export-all-layers` change.
 *
 * Takes a freshly-built KMZ Blob (see `./kmzBuilder.ts`) and invokes the
 * browser's standard "anchor-with-download-attribute" dance to push the
 * bytes to the user's Downloads folder without navigating away.
 *
 * Contract:
 *   1. Create an object URL for the blob.
 *   2. Build an anonymous `<a>` element with the URL + requested filename.
 *   3. Mount it in the DOM (required by some older browsers — Firefox
 *      historically ignored clicks on detached anchors).
 *   4. Click once.
 *   5. Remove the anchor from the DOM.
 *   6. Revoke the object URL — CRITICAL: without this the blob stays
 *      pinned for the life of the document, which for a multi-MB KMZ is a
 *      real leak.
 *
 * Separated from `kmzBuilder.ts` so the builder stays a pure function
 * (easier to test, reusable in a worker if we ever move there).
 */

export function triggerKmzDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
