# Windows signing status and Smart App Control

The published **0.5.0-beta.1 is unsigned**. It may be blocked on PCs enforcing Smart App Control. It has not passed a clean-machine SAC installation test. GitHub hosting, SHA-256 checks, a Beta label, and antivirus scans do not substitute for a trusted Windows code-signing certificate.

## Verified inventory

The actual GitHub release installer and payload were inspected without executing their contents. The inventory includes PE executables, DLLs, Python native extensions, Rhino plug-ins and PowerShell scripts, including files nested in wheels and Yak archives.

- 425 archive entries represent 241 distinct file contents.
- 61 distinct contents have a valid Authenticode signature on the audit PC.
- 180 distinct contents are unsigned, including the Toolkit installer, Rhino plug-in, bundled Python interpreter and uv.

Some archive entries are templates or platform alternatives that the installer never executes. This inventory does not claim that every entry was blocked. Conversely, generated console launchers and native files extracted by .NET must also be checked after installation; inspecting only the outer EXE is insufficient.

## Release gate

`scripts/signing_inventory.py` stages executable contents under `.build` without running them. `scripts/audit_signatures.ps1` verifies those staged bytes and records Authenticode trust. The release workflow uploads the audit with the test artifact and prevents a new public release when the inventory contains unsigned or untrusted content. An already-published immutable release is left unchanged.

This gate is deliberately conservative. Passing it alone does not certify SAC compatibility: test installation, normal startup, CAD plug-in loading, per-user environments, update, repair, and uninstall on a separate SAC-enforced Windows PC before making that claim. Do not disable protection on end-user computers as an installation requirement.

## Remaining external requirement

There is currently no usable public-trust code-signing certificate in the development PC's personal or machine certificate store. No signing service has been enrolled, no certificate has been purchased, and no signing request or identity document has been submitted.

- **Free OSS signing:** SignPath Foundation requires project review and approval. It has conditions on open-source licensing, forks and third-party binaries. Approval of the Toolkit alone does not authorize signing unsigned upstream Python, uv or native wheels under the Foundation certificate. Obtain an explicit coverage agreement first.
- **Personal, including closed-source software:** investigate a publicly trusted individual code-signing certificate and cloud/HSM signing service. Publisher identity verification is still required. This usually avoids OSS-project eligibility review, but is a paid service and requires the owner's selection and enrollment.
- **Cloudflare:** its public SSL/TLS certificate offerings secure websites; they are not Windows Authenticode signing certificates.

Do not generate a self-signed certificate and label it as a public-trust SAC fix. Do not upload a private key or identity document to this repository.

Once a provider is selected, integrate signing into the immutable build: sign the allowed native content; rebuild wheels/Yak and dependency hashes as necessary; build the payload; sign the final installer; generate final release hashes; verify coverage; run SAC-enforced tests; then publish a **new** version. Do not silently replace 0.5.0-beta.1 assets.

References: [Microsoft SAC signing](https://learn.microsoft.com/en-us/windows/apps/develop/smart-app-control/code-signing-for-smart-app-control), [Microsoft SAC testing](https://learn.microsoft.com/windows/apps/develop/smart-app-control/test-your-app-with-smart-app-control), [SignPath Foundation conditions](https://signpath.org/terms), [Cloudflare certificates](https://developers.cloudflare.com/ssl/edge-certificates/).
