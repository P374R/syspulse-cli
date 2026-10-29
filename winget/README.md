# Submitting SysPulse to Winget (Windows Package Manager)

Microsoft provides an official CLI tool called `wingetcreate` to publish any release directly into Winget.

### One-Command Submission:

1. Create a GitHub Release (e.g. `v1.0.0`) on `https://github.com/P374R/syspulse-cli` with `syspulse-windows-x64.exe` attached.
2. Run this command in Windows PowerShell:
   ```powershell
   winget install wingetcreate
   wingetcreate new https://github.com/P374R/syspulse-cli/releases/download/v1.0.0/syspulse-windows-x64.exe
   ```
3. Set PackageIdentifier to: `P374R.SysPulse`
4. `wingetcreate` automatically calculates the SHA256 hash and submits the Pull Request to `microsoft/winget-pkgs` for you!

Once approved, anyone in the world installs it with:
```powershell
winget install P374R.SysPulse
```
And immediately launches it with:
```powershell
syspulse
```
