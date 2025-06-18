document.addEventListener("DOMContentLoaded", () => {
  // Fetch models and populate table
  fetch("http://127.0.0.1:8000/models")
    .then(res => res.json())
    .then(models => {
      const tbody = document.getElementById("models-table-body");
      models.forEach(modelName => {
        const tr = document.createElement("tr");

        // Model name cell
        const tdModel = document.createElement("td");
        tdModel.innerHTML = `<strong>${modelName}</strong>`;
        tr.appendChild(tdModel);

        // Placeholder cells for other columns
        for (let i = 1; i < 6; i++) {
          const td = document.createElement("td");
          td.textContent = "-";
          tr.appendChild(td);
        }

        tbody.appendChild(tr);
      });
    })
    .catch(err => console.error("Failed to load models:", err));

  // Smooth scrolling for navigation links
  document.querySelectorAll('.nav-links a').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      e.preventDefault();
      const target = document.querySelector(this.getAttribute('href'));
      if (target) {
        target.scrollIntoView({
          behavior: 'smooth',
          block: 'start'
        });
      }
    });
  });

  // Add hover effects to scorecard cells
  document.querySelectorAll('.scorecard-cell').forEach(cell => {
    if (!cell.classList.contains('scorecard-model') && !cell.classList.contains('scorecard-header')) {
      cell.addEventListener('mouseenter', function () {
        this.style.transform = 'scale(1.05)';
        this.style.transition = 'transform 0.2s ease';
      });

      cell.addEventListener('mouseleave', function () {
        this.style.transform = 'scale(1)';
      });
    }
  });

  // Add active state to navigation on scroll
  window.addEventListener('scroll', function () {
    const sections = document.querySelectorAll('.section');
    const navLinks = document.querySelectorAll('.nav-links a');

    let current = '';
    sections.forEach(section => {
      const sectionTop = section.offsetTop - 100;
      if (window.pageYOffset >= sectionTop) {
        current = section.getAttribute('id');
      }
    });

    navLinks.forEach(link => {
      link.style.backgroundColor = '';
      if (link.getAttribute('href') === '#' + current) {
        link.style.backgroundColor = '#e9ecef';
      }
    });
  });
});
