// Function to load HTML components
async function loadComponent(elementId, componentPath, callback) {
  try {
    const response = await fetch(componentPath);
    if (!response.ok) {
      throw new Error(`Error loading component: ${response.statusText}`);
    }
    const html = await response.text();
    document.getElementById(elementId).innerHTML = html;
    if (typeof callback === "function") callback();
  } catch (error) {
    console.error("Error loading component:", error);
  }
}

// Burger menu logic as a function
function setupBurgerMenu() {
  const burger = document.querySelector(".burger-menu");
  const navMenu = document.getElementById("nav-menu");
  if (burger && navMenu) {
    // Ensure menu is closed by default
    navMenu.classList.remove("open");
    burger.classList.remove("open");
    burger.setAttribute("aria-expanded", "false");
    burger.addEventListener("click", function () {
      const isOpen = navMenu.classList.toggle("open");
      burger.classList.toggle("open");
      burger.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });
    // Close menu when a nav link is clicked (on mobile)
    navMenu.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        if (window.innerWidth <= 992) {
          navMenu.classList.remove("open");
          burger.classList.remove("open");
          burger.setAttribute("aria-expanded", "false");
        }
      });
    });
    // Remove open class on resize to desktop
    window.addEventListener("resize", function () {
      if (window.innerWidth > 992) {
        navMenu.classList.remove("open");
        burger.classList.remove("open");
        burger.setAttribute("aria-expanded", "false");
      }
    });
  }
}

// Load components when the DOM is fully loaded
// Call setupBurgerMenu after header is loaded

document.addEventListener("DOMContentLoaded", () => {
  // Detect if we're on an English page
  const isEnglishPage =
    window.location.pathname.startsWith("/en/") ||
    document.documentElement.lang === "en" ||
    document.documentElement.dir === "ltr";

  // Load appropriate header and footer based on language
  const headerPath = isEnglishPage
    ? "static/components/header-en.html"
    : "static/components/header.html";
  const footerPath = isEnglishPage
    ? "static/components/footer-en.html"
    : "static/components/footer.html";

  loadComponent("header-component", headerPath, setupBurgerMenu);
  loadComponent("footer-component", footerPath);
});
