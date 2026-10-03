(function () {
  "use strict";

  var root = document.documentElement;

  // ── Tema claro / oscuro ────────────────────────────────────────────────────
  var toggle = document.querySelector("[data-theme-toggle]");
  if (toggle) {
    toggle.addEventListener("click", function () {
      var dark = root.dataset.theme
        ? root.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
      try {
        localStorage.setItem("codea2-theme", root.dataset.theme);
      } catch (error) {
        // Sin almacenamiento local el cambio dura lo que dure la página
      }
    });
  }

  // ── Tooltip ────────────────────────────────────────────────────────────────
  // Uno solo para toda la página. Se rellena con textContent: los textos vienen de los
  // JSON subidos y no se interpretan nunca como HTML.
  var tip = document.getElementById("tip");
  var tipValue = tip.querySelector("strong");
  var tipLines = tip.querySelectorAll("span");
  var current = null;

  function showTip(target, x, y) {
    if (current !== target) {
      current = target;
      tipValue.textContent = target.dataset.tipValue || "";
      tipLines[0].textContent = target.dataset.tip || "";
      tipLines[1].textContent = target.dataset.tipNote || "";
      tip.hidden = false;
    }
    var box = tip.getBoundingClientRect();
    var left = Math.min(x + 14, window.innerWidth - box.width - 8);
    var top = y + 18;
    if (top + box.height > window.innerHeight - 8) {
      top = y - box.height - 12;
    }
    tip.style.left = Math.max(left, 8) + "px";
    tip.style.top = Math.max(top, 8) + "px";
  }

  function hideTip() {
    current = null;
    tip.hidden = true;
  }

  document.addEventListener("pointermove", function (event) {
    var target = event.target.closest ? event.target.closest("[data-tip]") : null;
    if (target) {
      showTip(target, event.clientX, event.clientY);
    } else if (current) {
      hideTip();
    }
  });
  document.addEventListener("pointerleave", hideTip);
  document.addEventListener("focusin", function (event) {
    var target = event.target.closest ? event.target.closest("[data-tip]") : null;
    if (target) {
      var box = target.getBoundingClientRect();
      showTip(target, box.left + box.width / 2, box.bottom);
    }
  });
  document.addEventListener("focusout", hideTip);
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape") {
      hideTip();
    }
  });
  window.addEventListener("scroll", hideTip, { passive: true });

  // ── Filtros: aplicar al cambiar ────────────────────────────────────────────
  document.querySelectorAll("form[data-autosubmit]").forEach(function (form) {
    form.addEventListener("change", function (event) {
      if (event.target.matches("select, input[type=date], input[type=checkbox]")) {
        form.requestSubmit ? form.requestSubmit() : form.submit();
      }
    });
  });

  // ── Tablas ordenables ──────────────────────────────────────────────────────
  function cellValue(row, index) {
    var cell = row.cells[index];
    if (!cell) {
      return "";
    }
    return cell.dataset.v !== undefined ? cell.dataset.v : cell.textContent.trim();
  }

  document.querySelectorAll("table[data-sortable]").forEach(function (table) {
    var headers = table.tHead.rows[table.tHead.rows.length - 1].cells;
    Array.prototype.forEach.call(headers, function (th, index) {
      var button = th.querySelector("button.sort");
      if (!button) {
        return;
      }
      button.addEventListener("click", function () {
        var ascending = th.getAttribute("aria-sort") !== "ascending";
        Array.prototype.forEach.call(headers, function (other) {
          other.removeAttribute("aria-sort");
        });
        th.setAttribute("aria-sort", ascending ? "ascending" : "descending");

        var numeric = th.classList.contains("n");
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var x = cellValue(a, index);
          var y = cellValue(b, index);
          var order;
          if (numeric) {
            // Lo vacío va siempre al final, ordene como ordene
            if (x === "" || y === "") {
              return (x === "") - (y === "");
            }
            order = parseFloat(x) - parseFloat(y);
          } else {
            order = x.localeCompare(y, "es", { numeric: true });
          }
          return ascending ? order : -order;
        });
        rows.forEach(function (row) {
          body.appendChild(row);
        });
      });
    });
  });

  // ── Buscar dentro de una tabla ─────────────────────────────────────────────
  document.querySelectorAll("input[data-table-filter]").forEach(function (input) {
    var table = document.getElementById(input.dataset.tableFilter);
    var counter = document.querySelector("[data-filter-count='" + input.dataset.tableFilter + "']");
    input.addEventListener("input", function () {
      var words = input.value.toLowerCase().split(/\s+/).filter(Boolean);
      var shown = 0;
      Array.prototype.forEach.call(table.tBodies[0].rows, function (row) {
        var text = row.textContent.toLowerCase();
        var match = words.every(function (word) {
          return text.indexOf(word) !== -1;
        });
        row.hidden = !match;
        shown += match;
      });
      if (counter) {
        counter.textContent = words.length ? shown + " coinciden" : "";
      }
    });
  });

  // ── Incluir o excluir una sesión sin recargar ──────────────────────────────
  document.querySelectorAll("form[data-state-toggle]").forEach(function (form) {
    // Sin JavaScript queda el botón; con él, la casilla guarda al momento
    var box = form.querySelector("input[type=checkbox]");
    box.closest("label").hidden = false;
    form.querySelector("button").hidden = true;
    box.addEventListener("change", function () {
      var data = new FormData();
      data.append("csrf", form.elements.csrf.value);
      data.append("excluded", box.checked ? "0" : "1");
      fetch(form.action, {
        method: "POST",
        body: data,
        headers: { "X-Requested-With": "fetch" },
        credentials: "same-origin"
      }).then(function (response) {
        if (!response.ok) {
          throw new Error(response.status);
        }
        var row = form.closest("tr");
        if (row) {
          row.classList.toggle("dim", !box.checked);
          var tag = row.querySelector("[data-excluded-tag]");
          if (tag) {
            tag.hidden = box.checked;
          }
        }
        var note = document.querySelector("[data-stale-note]");
        if (note) {
          note.hidden = false;
        }
      }).catch(function () {
        box.checked = !box.checked;
        window.alert("No se pudo guardar el cambio. Recarga la página y vuelve a intentarlo.");
      });
    });
  });
})();
