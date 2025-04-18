// Enhanced navigation functionality
document.addEventListener("DOMContentLoaded", function () {
  // Table of contents generation
  const toc = document.createElement("div");
  toc.classList.add("table-of-contents");
  toc.innerHTML = '<h3>Table of Contents</h3><ul class="toc-list"></ul>';

  const tocList = toc.querySelector(".toc-list");
  const sections = document.querySelectorAll("main section");

  sections.forEach((section) => {
    const sectionId = section.getAttribute("id");
    const sectionTitle = section.querySelector("h2").textContent;
    const listItem = document.createElement("li");

    const link = document.createElement("a");
    link.href = "#" + sectionId;
    link.textContent = sectionTitle;

    listItem.appendChild(link);
    tocList.appendChild(listItem);

    // Create subsection links if needed
    const subsections = section.querySelectorAll("h3");
    if (subsections.length > 0) {
      const subList = document.createElement("ul");
      subsections.forEach((subsection) => {
        const subId =
          sectionId +
          "-" +
          subsection.textContent
            .toLowerCase()
            .replace(/\s+/g, "-")
            .replace(/[^\w-]/g, "");
        subsection.id = subId;

        const subItem = document.createElement("li");
        const subLink = document.createElement("a");
        subLink.href = "#" + subId;
        subLink.textContent = subsection.textContent;
        subLink.classList.add("toc-subsection");

        subItem.appendChild(subLink);
        subList.appendChild(subItem);
      });
      listItem.appendChild(subList);
    }
  });

  // Insert TOC after the executive summary
  const executiveSummary = document.querySelector("#executive-summary");
  if (executiveSummary) {
    executiveSummary.parentNode.insertBefore(toc, executiveSummary.nextSibling);
  }

  // Smooth scrolling for all internal links
  document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
    anchor.addEventListener("click", function (e) {
      e.preventDefault();
      const targetId = this.getAttribute("href");
      const targetElement = document.querySelector(targetId);

      if (targetElement) {
        window.scrollTo({
          top: targetElement.offsetTop - 70, // Adjust for fixed header
          behavior: "smooth",
        });

        // Update URL without page reload
        history.pushState(null, null, targetId);
      }
    });
  });

  // Highlight current section in navigation
  const navLinks = document.querySelectorAll("nav a");

  function highlightCurrentSection() {
    let currentSectionId = "";
    const scrollPosition = window.scrollY;

    sections.forEach((section) => {
      const sectionTop = section.offsetTop - 100;
      const sectionBottom = sectionTop + section.offsetHeight;

      if (scrollPosition >= sectionTop && scrollPosition < sectionBottom) {
        currentSectionId = section.getAttribute("id");
      }
    });

    navLinks.forEach((link) => {
      link.classList.remove("active");
      if (link.getAttribute("href") === "#" + currentSectionId) {
        link.classList.add("active");
      }
    });

    // Also highlight in TOC
    document.querySelectorAll(".toc-list a").forEach((link) => {
      link.classList.remove("active");
      if (link.getAttribute("href") === "#" + currentSectionId) {
        link.classList.add("active");
      }
    });
  }

  window.addEventListener("scroll", highlightCurrentSection);
  highlightCurrentSection(); // Initial call

  // Add collapsible functionality to sections
  document.querySelectorAll("section h2").forEach((header) => {
    const section = header.parentElement;
    const content = section.querySelector(".content-box");

    header.classList.add("collapsible");
    header.innerHTML += '<span class="collapse-icon"></span>';

    header.addEventListener("click", function (e) {
      // Don't collapse if clicking on a link inside the header
      if (e.target.tagName === "A") return;

      this.classList.toggle("collapsed");

      if (content.style.maxHeight) {
        content.style.maxHeight = null;
      } else {
        content.style.maxHeight = content.scrollHeight + "px";
      }
    });
  });

  // Initialize MathJax if available
  if (typeof renderMathInElement === "function") {
    renderMathInElement(document.body, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
      ],
    });
  }
});
