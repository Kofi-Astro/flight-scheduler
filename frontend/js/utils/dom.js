/**
 * Minimal DOM helpers.
 *
 * We build UI by composing small functions that return real DOM nodes — no
 * virtual DOM, no template strings with innerHTML (which invites XSS). `el()`
 * is the workhorse.
 */

/**
 * Create an element.
 *
 * @param {string} tag            e.g. "div", "button.btn.btn--primary#save"
 * @param {object} [attrs]        properties/attributes. Special keys:
 *                                  - class / className
 *                                  - dataset: {key: value}
 *                                  - on: {event: handler}
 *                                  - html: trusted innerHTML (use sparingly)
 * @param {...(Node|string|Array|null|false)} children
 * @returns {HTMLElement}
 *
 * @example
 *   el("button.btn.btn--primary", { on: { click: save } }, "Save")
 */
export function el(tag, attrs = {}, ...children) {
  // Support "tag.class.class#id" shorthand.
  const [head, ...classShorthand] = tag.split(".");
  let tagName = head;
  let id = null;
  if (tagName.includes("#")) {
    [tagName, id] = tagName.split("#");
  }
  const node = document.createElement(tagName || "div");
  if (id) node.id = id;
  for (const cls of classShorthand) {
    if (cls.includes("#")) {
      const [c, i] = cls.split("#");
      if (c) node.classList.add(c);
      if (i) node.id = i;
    } else {
      node.classList.add(cls);
    }
  }

  for (const [key, value] of Object.entries(attrs || {})) {
    if (value == null || value === false) continue;
    if (key === "class" || key === "className") {
      node.className = [node.className, value].filter(Boolean).join(" ");
    } else if (key === "dataset") {
      Object.assign(node.dataset, value);
    } else if (key === "on") {
      for (const [evt, handler] of Object.entries(value)) node.addEventListener(evt, handler);
    } else if (key === "html") {
      node.innerHTML = value;
    } else if (key === "style" && typeof value === "object") {
      Object.assign(node.style, value);
    } else if (key in node) {
      node[key] = value;
    } else {
      node.setAttribute(key, value);
    }
  }

  appendChildren(node, children);
  return node;
}

function appendChildren(node, children) {
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

/** Remove all children from a node. */
export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

/** Replace a node's contents with new children. */
export function render(node, ...children) {
  clear(node);
  appendChildren(node, children);
  return node;
}

/** Query shorthand. */
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

/** Debounce — used by the airport autocomplete. */
export function debounce(fn, ms = 200) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}
