/* Cascading Type > Subtype > Item selects for ticket categorization.
 * typesData shape: [{id, name, subtypes: [{id, name, items: [{id, name}]}]}]
 */
function initCategorySelects(typesData, typeElId, subtypeElId, itemElId, selType, selSubtype, selItem) {
  const typeEl = document.getElementById(typeElId);
  const subtypeEl = document.getElementById(subtypeElId);
  const itemEl = document.getElementById(itemElId);
  if (!typeEl || !subtypeEl || !itemEl) return;

  function findType(id) {
    return typesData.find(function (t) { return t.id === id; });
  }
  function findSubtype(id) {
    for (const t of typesData) {
      const st = t.subtypes.find(function (s) { return s.id === id; });
      if (st) return st;
    }
    return null;
  }
  function fillSelect(el, options, placeholder, selectedId) {
    el.innerHTML = "";
    const blank = document.createElement("option");
    blank.value = "";
    blank.textContent = placeholder;
    el.appendChild(blank);
    options.forEach(function (opt) {
      const o = document.createElement("option");
      o.value = opt.id;
      o.textContent = opt.name;
      if (selectedId && opt.id === selectedId) o.selected = true;
      el.appendChild(o);
    });
  }

  function onTypeChange(preserveSubtype, preserveItem) {
    const t = findType(parseInt(typeEl.value, 10));
    fillSelect(subtypeEl, t ? t.subtypes : [], "Select subtype", preserveSubtype);
    onSubtypeChange(preserveItem);
  }
  function onSubtypeChange(preserveItem) {
    const st = findSubtype(parseInt(subtypeEl.value, 10));
    fillSelect(itemEl, st ? st.items : [], "Select item", preserveItem);
  }

  typeEl.addEventListener("change", function () { onTypeChange(null, null); });
  subtypeEl.addEventListener("change", function () { onSubtypeChange(null); });

  // Initial render, preserving any pre-selected values (edit forms).
  onTypeChange(selSubtype || null, selItem || null);
}
