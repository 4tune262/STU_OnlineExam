let draggedItem = null;

document.addEventListener('dragstart', function(e) {
    if (e.target.classList.contains('draggable-badge') || e.target.classList.contains('sort-item')) {
        draggedItem = e.target;
        e.dataTransfer.setData('text/plain', e.target.id);
    }
});

document.addEventListener('dragover', function(e) {
    e.preventDefault();
    let target = e.target.closest('.blank-slot, .sort-box, .source-pool');
    if (target && target.classList.contains('blank-slot')) {
        target.classList.add('drag-over');
    }
});

document.addEventListener('dragleave', function(e) {
    let target = e.target.closest('.blank-slot');
    if (target) {
        target.classList.remove('drag-over');
    }
});

document.addEventListener('drop', function(e) {
    e.preventDefault();
    let target = e.target.closest('.blank-slot, .sort-box, .source-pool');
    if (!target || !draggedItem) return;

    if (target.classList.contains('blank-slot')) {
        target.classList.remove('drag-over');
        let existingItem = target.querySelector('.draggable-badge');
        if (existingItem) {
            let qId = target.getAttribute('data-qid');
            let pool = document.getElementById(`pool-drag-${qId}`);
            if (pool) pool.appendChild(existingItem);
        }
        target.innerHTML = '';
        target.appendChild(draggedItem);
        draggedItem.style.margin = "0";
    } else if (target.classList.contains('sort-box') || target.classList.contains('source-pool')) {
        let placeholder = target.querySelector('.fst-italic');
        if (placeholder) placeholder.remove();

        target.appendChild(draggedItem);
        if(draggedItem.classList.contains('draggable-badge')) {
            draggedItem.style.margin = "4px";
        }
    }
});

// Gom dữ liệu trước khi submit form
function prepareExamSubmission() {
    // Gom dữ liệu Sort
    document.querySelectorAll('.sort-box.target-right').forEach(box => {
        let qId = box.id.split('-')[2];
        let items = box.querySelectorAll('.sort-item');
        let ids = Array.from(items).map(item => item.getAttribute('data-id'));
        let inputField = document.getElementById(`sorted-input-${qId}`);
        if (inputField) inputField.value = JSON.stringify(ids);
    });

    // Gom dữ liệu Drag điền khuyết
    document.querySelectorAll('.blank-slot').forEach(slot => {
        let qId = slot.getAttribute('data-qid');
        let blankIndex = slot.getAttribute('data-index');
        let item = slot.querySelector('.draggable-badge');
        let hiddenInput = document.getElementById(`drag-val-${qId}-${blankIndex}`);
        if (hiddenInput) {
            hiddenInput.value = item ? item.getAttribute('data-id') : "";
        }
    });
}