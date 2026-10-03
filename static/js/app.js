const sidebar = document.getElementById("sidebar");
const menu = document.getElementById("menu-btn");

if (sidebar && menu && window.matchMedia("(max-width: 767.98px)").matches) {
  sidebar.classList.add("hide");
  menu.setAttribute("aria-expanded", "false");
}

menu?.addEventListener("click", () => {
  const isCollapsed = sidebar?.classList.toggle("hide") ?? false;
  menu.setAttribute("aria-expanded", String(!isCollapsed));
});
