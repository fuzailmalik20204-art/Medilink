# MediLink demo deployment

This project deploys the static frontend to Netlify and the FastAPI backend with
PostgreSQL to Render.

## Deploy the backend to Render

1. Push this project to a Git repository and connect it to Render.
2. In Render, create a Blueprint instance from the repository's `render.yaml`.
   It defines the API service and PostgreSQL database.
3. The Blueprint already sets `ALLOWED_ORIGINS` to
   `https://medilinkhealth.netlify.app`. If you use a different Netlify site
   URL or custom domain, update that value in `render.yaml` before syncing the
   Blueprint.
4. Wait for the API service to finish deploying. Check that its `/` URL returns
   a JSON response with `"status": "Backend is running"`.

The Render service runs Alembic migrations before starting the API. Render
generates the `SECRET_KEY` and supplies the PostgreSQL connection string.
The Visit Brief extracts text from saved medical records, PDFs, DOCX files,
and OCR-supported image/scanned PDF pages. Render installs Tesseract OCR for
scanned files. Extracted content is processed by the MediLink backend and is
not sent to an external AI service. Legacy `.doc` files must be converted to
PDF or DOCX before their contents can be included.

## Deploy the frontend to Netlify

1. Import the same Git repository into Netlify. The root `netlify.toml` sets the
   publish directory to `frontend`; no build command is required.
2. Copy the deployed Render API's base URL (for example,
   `https://medilink-api.onrender.com`) into
   `frontend/config.js` as `window.MEDILINK_API_BASE_URL`. Do not add `/api` to
   the end of the URL.
3. Commit and push that setting so Netlify redeploys the frontend.

An empty API URL in `frontend/config.js` preserves local development by using
the current page's host on port 8000.

## Demo limitations

The free Render database is temporary and may expire; use only throwaway demo
data. Uploaded files are stored on the web service's local filesystem, which
is not persistent across deployments/restarts on the free plan. The Visit
Brief reports missing files instead of including their contents. Do not store
real patient information or rely on this setup for production.
