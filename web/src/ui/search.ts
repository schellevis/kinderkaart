/**
 * Search bar UI component.
 */

export interface SearchBarOptions {
  placeholder?: string;
  initialValue?: string;
  onInput: (value: string) => void;
}

export function createSearchBar(opts: SearchBarOptions): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.className = "search-bar";
  wrapper.setAttribute("role", "search");

  const input = document.createElement("input");
  input.type = "search";
  input.placeholder = opts.placeholder ?? "Zoek activiteiten…";
  input.value = opts.initialValue ?? "";
  input.setAttribute("aria-label", "Zoek activiteiten");
  input.setAttribute("autocomplete", "off");
  input.setAttribute("spellcheck", "false");

  let debounce: ReturnType<typeof setTimeout> | null = null;
  input.addEventListener("input", () => {
    if (debounce) clearTimeout(debounce);
    debounce = setTimeout(() => opts.onInput(input.value), 200);
  });

  // Clear on Escape
  input.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      input.value = "";
      opts.onInput("");
    }
  });

  const icon = document.createElement("span");
  icon.textContent = "🔍";
  icon.setAttribute("aria-hidden", "true");

  wrapper.appendChild(icon);
  wrapper.appendChild(input);

  return wrapper;
}

export function getSearchInput(bar: HTMLElement): HTMLInputElement | null {
  return bar.querySelector("input");
}
