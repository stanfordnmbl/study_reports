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
   git clone --depth 1 https://github.com/opensim-org/opensim-viewer-backend.git vendors\opensim-viewer-backend
   ```

4. Download viewer build
   ```powershell
   curl https://github.com/opensim-org/opensim-viewer/releases/download/headless-0.1/viewer-build.zip  -OutFile "viewer-build.zip"
   ```
   
5. Extract viewer build
   ```powershell
  Expand-Archive -Path ".\viewer-build.zip" -DestinationPath ".\viewer-build"
   ```

6. Install playwright to drive the animation and capture movie
 - At the .venv prompt, type
 > playwright install

 7. From here on you can run the script 
 > python generate_report.py <full_path_to_data_folder_eg_ID119>

 8. Inspecting report
 - The above script will create two subfolders under <full_path_to_data_folder_eg_ID119>
   - work/*.gltf these are the gltf files that you can inspect for content using the online viewer at
   https://gltf-viewer.donmccurdy.com/ or
   https://opensim-viewer-git-headless-ayman-habib-s-projects.vercel.app/ (not sure if availble publicly)
   - movies/*.mp4
   - smart_study_report.html (intermediate report with videos external mainly for tune up/experimenting)
   - smart_study_report_embedded.html finished report with embedded videos

   

