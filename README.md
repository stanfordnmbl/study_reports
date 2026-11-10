# Report creation tools

Tools for creating participant reports for various studies utilizing OpenSim ecosystem

## Getting started (Windows)

You need Python 3.11+ and git. 

1. Clone the repo and create a virtual environment:

   ```powershell
   git clone https://github.com/stanfordnmbl/study_reports.git
   cd study_reports
   py -3.13 -m venv .venv
   .venv/Scripts/activate
   ```

2. Install the requirements

   ```powershell
   pip install -r requirements.txt"
   ```

3. Add the OpenSim viewer backend, which exports the model to 3D:

   ```powershell
   git clone --depth 1 https://github.com/opensim-org/opensim-viewer-backend.git vendor\opensim-viewer-backend
   ```

4. Download viewer build
   ```powershell
   curl https://github.com/opensim-org/opensim-viewer/releases/download/headless-0.1/viewer-build.zip  -OutFile "viewer-build.zip"
   ```
   
5. Extract viewer build
   ```powershell
  Expand-Archive -Path ".\viewer-build.zip" -DestinationPath ".\viewer-build"
   ```

