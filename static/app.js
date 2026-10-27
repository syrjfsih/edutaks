document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-filter]").forEach((input) => {
    input.addEventListener("input", () => {
      const table = document.getElementById(input.dataset.filter);
      if (!table) return;
      const q = input.value.toLowerCase();
      table.querySelectorAll("tbody tr").forEach((row) => {
        row.style.display = row.innerText.toLowerCase().includes(q)
          ? ""
          : "none";
      });
    });
  });
  const form = document.getElementById("lecturer-task-form");
  if (form) {
    const action = document.getElementById("task-action"),
      id = document.getElementById("task-id"),
      title = document.getElementById("task-title"),
      description = document.getElementById("task-description"),
      deadline = document.getElementById("task-deadline"),
      prodi = document.getElementById("task-prodi"),
      course = document.getElementById("task-course"),
      heading = document.getElementById("task-form-title"),
      submit = document.getElementById("task-submit"),
      cancel = document.getElementById("task-cancel");
    const updateCourses = () => {
      let first = "";
      [...course.options].forEach((o) => {
        if (!o.value) return;
        o.hidden = !!prodi.value && o.dataset.prodi !== prodi.value;
        if (!o.hidden && !first) first = o.value;
      });
      if (course.selectedOptions[0]?.hidden) course.value = first;
    };
    prodi.addEventListener("change", updateCourses);
    document.querySelectorAll("[data-edit]").forEach((btn) =>
      btn.addEventListener("click", () => {
        let t;
        try {
          t = JSON.parse(btn.dataset.edit);
        } catch (e) {
          return;
        }
        action.value = "edit";
        id.value = t.id;
        title.value = t.title;
        description.value = t.description;
        deadline.value = t.deadline;
        prodi.value = t.prodi;
        updateCourses();
        course.value = t.course;
        heading.textContent = "Edit tugas";
        submit.innerHTML = "Simpan perubahan →";
        cancel.classList.remove("hidden");
        form.scrollIntoView({ behavior: "smooth", block: "start" });
      }),
    );
    const reset = () => {
      form.reset();
      action.value = "create";
      id.value = "";
      heading.textContent = "Buat tugas baru";
      submit.innerHTML = "Simpan tugas →";
      cancel.classList.add("hidden");
      updateCourses();
    };
    cancel.addEventListener("click", reset);
    updateCourses();
  }
});
