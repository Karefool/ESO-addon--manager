@echo off
echo Building React Frontend...
cd frontend
call npm run build
cd ..

echo Building Native Executable...
pyinstaller --noconfirm --onedir --windowed --add-data "frontend/dist;frontend/dist" --name "ESO_Power_Lite" main.py

echo Build complete! Your standalone executable is in the "dist/ESO_Power_Lite" folder.
pause
