"use strict";

// CONSTRAINTS 
const DESCRIPTION_MIN = 10;
const DESCRIPTION_MAX = 500;
const MAX_PHOTO_BYTES = 2 * 1024 * 1024;
const CELL_PATTERN = /^\+?[0-9 ]{10,15}$/;

const DRAFT_KEY = "ward42_report_draft";

const DRAFT_FIELDS = ["category", "street", "description"];
const DRAFT_MAX_AGE_MS = 7 * 24 * 60 * 60 * 1000;

const byId = (id) => document.getElementById(id);

// DEBOUNCE FUNCTION
function debounce(fn, delayMs) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delayMs);
    };
}

// LOCAL STORAGE DRAFT
// // CLEAR DRAFT FUNCTION
function clearDraft() {
    try {
        localStorage.removeItem(DRAFT_KEY);
    } catch (error) {
        console.warn("Could not clear the draft:", error);
    }
}

// LOAD DRAFT FUNCTION
function loadDraft() {
    try {
        const raw = localStorage.getItem(DRAFT_KEY);
        if (!raw) return null;

        const draft = JSON.parse(raw);
        if (typeof draft !== "object" || draft === null ||
            Date.now() - Number(draft.savedAt) > DRAFT_MAX_AGE_MS) {
            clearDraft();
            return null;
        }
        return draft;
    } catch (error) {
        console.warn("Ignoring an unreadable draft:", error);
        clearDraft();
        return null;
    }
}

// SAVE DRAFT FUNCTION
function saveDraft(form) {
    try {
        const draft = {};
        let hasContent = false;
        DRAFT_FIELDS.forEach((name) => {
            const field = form.elements[name];
            draft[name] = field ? field.value : "";
            if (draft[name].trim() !== "") hasContent = true;
        });

        if (!hasContent) {
            clearDraft();
            return;
        }
        draft.savedAt = Date.now();
        localStorage.setItem(DRAFT_KEY, JSON.stringify(draft));
    } catch (error) {
        console.warn("Could not save the draft:", error);
    }
}

// RESTORE DRAFT FUNCTION
function restoreDraft(form) {
    const draft = loadDraft();
    if (!draft) return;

    let restored = false;
    DRAFT_FIELDS.forEach((name) => {
        const field = form.elements[name];
        const value = draft[name];
        if (!field || typeof value !== "string" || value === "") return;

        if (field.tagName === "SELECT" &&
            !Array.from(field.options).some((option) => option.value === value)) {
            return;
        }
        field.value = value;
        restored = true;
    });

    if (restored) {
        byId("draft-notice").classList.remove("d-none");
        updateDescriptionCounter();
    }
}

// CLEAR DRAFT IF SUBMITTED FUNCTION
function clearDraftIfSubmitted() {
    if (byId("reference")) clearDraft();
}

// REPORT FORM VALIDATION 
const validators = {
    category: (field) => (field.value ? "" : "Please choose a category"),

    street: (field) => {
        const value = field.value.trim();
        if (!value) return "Please enter the street name";
        if (value.length > 100) return "The street name must be 100 characters or less";
        return "";
    },

    description: (field) => {
        const length = field.value.trim().length;
        if (length < DESCRIPTION_MIN) {
            return `Please write at least ${DESCRIPTION_MIN} characters so we can find the fault (you have ${length}).`;
        }
        if (length > DESCRIPTION_MAX) {
            return `Please shorten the description to ${DESCRIPTION_MAX} characters or less (you have ${length}).`;
        }
        return "";
    },

    resident_name: (field) => (field.value.trim() ? "" : "Please enter your name"),

    cell: (field) =>
        CELL_PATTERN.test(field.value.trim())
            ? ""
            : "Please enter a valid cell number, example 082 123 4567.",

    photo: (field) => {
        const file = field.files && field.files[0];
        if (!file) return "";
        if (!["image/jpeg", "image/png"].includes(file.type)) {
            return "The photo must be a JPG or PNG image";
        }
        if (file.size > MAX_PHOTO_BYTES) {
            const megabytes = (file.size / (1024 * 1024)).toFixed(1);
            return `This photo is ${megabytes} MB. Please choose one under 2 MB.`;
        }
        return "";
    },

    consent: (field) =>
        field.checked ? "" : "Please tick the box so we may contact you about this report",
};

// SHOW ERROR FUNCTION
function showError(field, message) {
    const box = byId(`${field.id}-error`);
    field.classList.toggle("is-invalid", message !== "");
    field.setAttribute("aria-invalid", message !== "" ? "true" : "false");
    if (box) box.textContent = message;
}

// VALIDATE FIELD FUNCTION
function validateField(field) {
    const check = validators[field.name];
    if (!check) return true;                              
    const message = check(field);
    showError(field, message);
    return message === "";
}

// VALIDATE ALL FUNCTION
function validateAll(form) {
    return Object.keys(validators)
        .map((name) => form.elements[name])
        .filter((field) => field && !validateField(field));
}

// DESCRIPTION COUNTER FUNCTION
function updateDescriptionCounter() {
    const field = byId("description");
    const counter = byId("description-count");
    if (field && counter) counter.textContent = `${field.value.length} / ${DESCRIPTION_MAX}`;
}

// INIT REPORT FORM FUNCTION
function initReportForm() {
    const form = byId("report-form");
    if (!form) return;                                   

    restoreDraft(form);
    updateDescriptionCounter();

    const saveSoon = debounce(() => saveDraft(form), 400);

    form.addEventListener("focusout", (event) => {
        if (event.target.name in validators) validateField(event.target);
    });


    const onChange = (event) => {
        const field = event.target;
        
        if (field.classList.contains("is-invalid")) validateField(field);
        if (field.id === "description") updateDescriptionCounter();
        if (DRAFT_FIELDS.includes(field.name)) saveSoon();  
    };
    form.addEventListener("input", onChange);
    form.addEventListener("change", onChange);

    form.addEventListener("submit", (event) => {
        const summary = byId("form-error-summary");
        try {
            const invalid = validateAll(form);
            if (invalid.length > 0) {
                event.preventDefault();
                summary.textContent =
                    `Please fix ${invalid.length} problem${invalid.length === 1 ? "" : "s"} below before submitting`;
                summary.classList.remove("d-none");
                invalid[0].focus();                             
            } else {
                summary.classList.add("d-none");
            }
        } catch (error) {
            console.error("Client-side validation could not run:", error);
        }
    });

    const discard = byId("discard-draft");
    if (discard) {
        discard.addEventListener("click", () => {
            clearDraft();
            DRAFT_FIELDS.forEach((name) => {
                if (form.elements[name]) form.elements[name].value = "";
            });
            updateDescriptionCounter();
            byId("draft-notice").classList.add("d-none");
            form.elements.category.focus();
        });
    }
}

// LIVE FILTER
function initReportFilter() {
    const form = byId("filter-form");
    const table = byId("reports-table");
    if (!form || !table) return;                         

    const categorySelect = byId("f-category");
    const statusSelect = byId("f-status");
    const count = byId("filter-count");

    const rows = Array.from(table.querySelectorAll("tbody tr[data-category]"));

    // APPLY FILTER FUNCTION
    function applyFilter() {
        const category = categorySelect.value;             
        const status = statusSelect.value;
        let visible = 0;

        rows.forEach((row) => {
            const matches =
                (category === "" || row.dataset.category === category) &&
                (status === "" || row.dataset.status === status);
            row.hidden = !matches;                  
            if (matches) visible += 1;
        });

        
        count.textContent =
            visible === 0
                ? "No reports match these filters."
                : `Showing ${visible} of ${rows.length} report${rows.length === 1 ? "" : "s"}.`;
    }

    categorySelect.addEventListener("change", applyFilter);
    statusSelect.addEventListener("change", applyFilter);
    form.addEventListener("submit", (event) => event.preventDefault());  

    
    byId("apply-filters").classList.add("d-none");
    applyFilter();
}

// PWA
// REGISTER SERVICE WORKER FUNCTION
function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;


    window.addEventListener("load", () => {
        navigator.serviceWorker
            .register("/service-worker.js")
            .then((registration) => console.info("Service worker registered, scope:", registration.scope))
            .catch((error) => console.error("Service worker registration failed:", error));
    });
}

// OFFLINE PAGE FUNCTION
function initOfflinePage() {
    const status = byId("draft-status");
    if (!status) return;                               

    status.textContent = loadDraft()
        ? "Your draft report is saved on this phone. When your signal returns, open Report a fault and your fault details will be filled in again. Your name and cell number are not saved, so you will type those again."
        : "You have no unsent draft on this phone, so nothing has been lost.";

    byId("retry").addEventListener("click", () => window.location.reload());
    
    window.addEventListener("online", () => window.location.reload());
}

// START EVERYTHING
document.addEventListener("DOMContentLoaded", () => {
    [clearDraftIfSubmitted, initReportForm, initReportFilter, initOfflinePage, registerServiceWorker].forEach((init) => {
        try {
            init();
        } catch (error) {
            console.error(`${init.name} failed:`, error);
        }
    });
});