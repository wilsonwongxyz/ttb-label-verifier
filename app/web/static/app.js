// Progressive enhancement only: the form works without this script.
(() => {
  const form = document.querySelector("[data-check-form]");
  if (!form) return;

  const MAX_EDGE = 2000; // big phone photos are shrunk before upload so slow links stay fast
  const fileInput = form.querySelector("#image");
  const preview = form.querySelector("[data-preview]");
  const imported = form.querySelector("[data-imported]");
  const originField = form.querySelector("[data-origin-field]");

  const showOrigin = () => { if (originField) originField.hidden = !imported.checked; };
  if (imported) { imported.addEventListener("change", showOrigin); showOrigin(); }

  async function shrink(file) {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = MAX_EDGE / Math.max(bitmap.width, bitmap.height);
    if (scale >= 1) return null;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d").drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.9));
    return blob && new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
  }

  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    const sampleField = form.querySelector("input[name=sample]");
    if (sampleField) sampleField.remove();
    preview.src = URL.createObjectURL(file);
    preview.closest("figure").hidden = false;
    const caption = preview.closest("figure").querySelector("figcaption");
    if (caption) caption.textContent = file.name;
    try {
      const smaller = await shrink(file);
      if (smaller) {
        const transfer = new DataTransfer();
        transfer.items.add(smaller);
        fileInput.files = transfer.files;
      }
    } catch {
      // Keep the original file; the server resizes it anyway.
    }
  });

  form.addEventListener("submit", () => {
    const button = form.querySelector("[data-submit]");
    button.disabled = true;
    button.textContent = "Checking…";
    form.querySelector("[data-working]").hidden = false;
  });
})();
