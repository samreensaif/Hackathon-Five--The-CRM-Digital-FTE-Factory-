# Web Support Form — Customer Success Digital FTE

A standalone React component that lets customers submit support tickets to the TaskFlow AI agent.

## What This Is

`SupportForm.jsx` is a single-file React component styled with Tailwind CSS. It provides:

- A professional support form with Name, Email, Subject, Category, Priority, and Message fields
- Client-side validation with inline error messages
- Loading state during submission
- Success screen with ticket ID confirmation
- Mobile-responsive design with TechCorp branding

## Test Locally

1. Start the FTE API server:
   ```bash
   cd 3-Specialization-Phase/production
   docker compose up
   ```

2. Open `index.html` directly in your browser:
   ```
   Just double-click index.html — no build step needed.
   ```

3. The form will POST to `http://localhost:8000/support/submit` by default.

## Change the API Endpoint

Edit the URL in `index.html`:

```html
<script>
  window.FTE_API_URL = "https://your-production-api.com/support/submit";
</script>
```

Or pass it as a prop when embedding:

```jsx
<SupportForm apiUrl="https://your-api.com/support/submit" />
```

## Embed in Any Website

### Option 1: Script Tags (simplest)

```html
<!-- Add to your HTML <head> -->
<script src="https://cdn.tailwindcss.com"></script>
<script crossorigin src="https://unpkg.com/react@18/umd/react.production.min.js"></script>
<script crossorigin src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js"></script>
<script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>

<!-- Add where you want the form to appear -->
<div id="support-form"></div>

<script>
  window.FTE_API_URL = "https://your-api.com/support/submit";
</script>
<script type="text/babel" src="SupportForm.jsx"></script>
<script type="text/babel">
  const root = ReactDOM.createRoot(document.getElementById("support-form"));
  root.render(<SupportForm />);
</script>
```

### Option 2: Import in a React App

```jsx
import SupportForm from "./SupportForm";

function App() {
  return <SupportForm apiUrl="https://your-api.com/support/submit" />;
}
```

Note: For production React apps, remove the `const { useState, useCallback } = React;` line from the component and use standard imports instead.

## Files

| File | Description |
|------|-------------|
| `SupportForm.jsx` | React component (single file, Tailwind CSS) |
| `index.html` | Test page — open directly in browser |
| `README.md` | This file |
