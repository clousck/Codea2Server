// Se carga en el <head>, antes de pintar: evita el destello de claro a oscuro.
(function () {
  try {
    var theme = localStorage.getItem("codea2-theme");
    if (theme === "light" || theme === "dark") {
      document.documentElement.dataset.theme = theme;
    }
  } catch (error) {
    // Sin almacenamiento local manda la preferencia del sistema
  }
})();
