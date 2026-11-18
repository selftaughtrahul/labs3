document.addEventListener("DOMContentLoaded", function () {
    var bar = document.getElementById("changelist-filter");
    if (!bar) return;

    bar.querySelectorAll("details").forEach(function (details) {
        var label = document.createElement("label");
        var name = document.createElement("span");
        var select = document.createElement("select");
        name.textContent = details.getAttribute("data-filter-title") || "Filter";
        details.querySelectorAll("a").forEach(function (link) {
            var option = document.createElement("option");
            option.value = link.getAttribute("href");
            option.textContent = link.textContent.trim();
            option.selected = link.parentElement.classList.contains("selected");
            select.appendChild(option);
        });
        select.addEventListener("change", function () {
            if (select.value) window.location.href = select.value;
        });
        label.append(name, select);
        details.replaceWith(label);
    });
});
