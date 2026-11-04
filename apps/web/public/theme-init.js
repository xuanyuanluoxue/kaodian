// 首屏前定主题，避免闪白；独立文件以满足 CSP script-src 'self'。
(function () {
  try {
    var saved = localStorage.getItem("kaodian:theme");
    if (saved !== "light" && saved !== "dark") {
      saved = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    document.documentElement.dataset.theme = saved;
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", saved === "dark" ? "#121412" : "#f7f7f5");
  } catch (e) {}
})();
