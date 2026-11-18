#!/usr/bin/env python3
"""Prepare a Rivulet checkout for self-signing & Apple TV deployment (height audio + FEL).

Usage:
    python3 Scripts/prepare-self-build.py --bundle-id com.iliasl.rivulet
"""

import argparse
import plistlib
import re
import shutil
import subprocess
import sys
from pathlib import Path


def resolve_repo(arg_path: str | None) -> Path:
    if arg_path:
        p = Path(arg_path).expanduser().resolve()
    elif (Path.cwd() / "Rivulet.xcodeproj").exists():
        p = Path.cwd().resolve()
    elif (Path.cwd() / "Rivulet" / "Rivulet.xcodeproj").exists():
        p = (Path.cwd() / "Rivulet").resolve()
    else:
        sys.exit("Error: Could not find Rivulet.xcodeproj. Pass --repo /path/to/Rivulet")
    if not (p / "Rivulet.xcodeproj" / "project.pbxproj").exists():
        sys.exit(f"Error: {p}/Rivulet.xcodeproj/project.pbxproj not found.")
    return p


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", help="Path to Rivulet checkout")
    parser.add_argument("--bundle-id", default="com.iliasl.rivulet", help="Unique bundle ID (default: com.iliasl.rivulet)")
    parser.add_argument("--team-id", default="", help="Optional Apple Developer Team ID")
    parser.add_argument("--no-fel", action="store_true", help="Only enable --height-audio (omit --fel)")
    args = parser.parse_args()

    repo = resolve_repo(args.repo)
    print(f"Preparing Rivulet checkout at: {repo}")

    # 1. Copy Secrets.swift template if missing
    secrets_dst = repo / "RivuletCore/Config/Secrets.swift"
    secrets_tpl = repo / "RivuletCore/Config/Secrets.swift.template"
    if not secrets_dst.exists():
        shutil.copyfile(secrets_tpl, secrets_dst)
        print("  [+] Created RivuletCore/Config/Secrets.swift from template")

    # 2. Enable AetherEngine enthusiast traits (--height-audio and optionally --fel)
    enthusiast_cmd = [sys.executable, "Scripts/enthusiast-build.py", "--height-audio"]
    if not args.no_fel:
        enthusiast_cmd.append("--fel")
    subprocess.run(enthusiast_cmd, cwd=repo, check=True)

    # 3. Strip restricted entitlements (CloudKit, AppAttest, Push, App Groups)
    entitlements_path = repo / "Rivulet/Rivulet.entitlements"
    with open(entitlements_path, "wb") as f:
        plistlib.dump({}, f)
    print("  [+] Cleared restricted entitlements in Rivulet/Rivulet.entitlements")

    # 4. Remove Apple-hosted BackgroundAssets keys from Rivulet/Info.plist
    info_plist_path = repo / "Rivulet/Info.plist"
    with open(info_plist_path, "rb") as f:
        info = plistlib.load(f)
    removed_keys = [k for k in ("BAAppGroupID", "BAHasManagedAssetPacks", "BAUsesAppleHosting") if k in info]
    for k in removed_keys:
        del info[k]
    with open(info_plist_path, "wb") as f:
        plistlib.dump(info, f, sort_keys=False)
    if removed_keys:
        print(f"  [+] Removed BackgroundAssets keys from Rivulet/Info.plist: {', '.join(removed_keys)}")

    # 5. Update project.pbxproj: Bundle ID, build number, Team ID, REGISTER_APP_GROUPS, detach extensions
    pbx_path = repo / "Rivulet.xcodeproj/project.pbxproj"
    pbx = pbx_path.read_text(encoding="utf-8")

    pbx = pbx.replace("com.gstudios.rivulet", args.bundle_id)
    pbx = pbx.replace("com.gstudios.RivuletTests", f"{args.bundle_id}.Tests")
    pbx = pbx.replace("REGISTER_APP_GROUPS = YES;", "REGISTER_APP_GROUPS = NO;")
    pbx = pbx.replace("CURRENT_PROJECT_VERSION = 93;", "CURRENT_PROJECT_VERSION = 129;")

    if args.team_id:
        pbx = re.sub(r"DEVELOPMENT_TEAM = [A-Z0-9]+;", f"DEVELOPMENT_TEAM = {args.team_id};", pbx)
    else:
        pbx = re.sub(r'\s*DEVELOPMENT_TEAM = ZHB786H6YN;\n', "\n", pbx)

    for line_pattern in [
        r'\s*A70B44472F05AF3200DEF5ED /\* Embed Foundation Extensions \*/,\n',
        r'\s*C40000050000000000000005 /\* Embed ExtensionKit Extensions \*/,\n',
        r'\s*A70B44412F05AF3200DEF5ED /\* PBXTargetDependency \*/,\n',
        r'\s*C400000E000000000000000E /\* PBXTargetDependency \*/,\n',
    ]:
        pbx = re.sub(line_pattern, "\n", pbx)

    pbx_path.write_text(pbx, encoding="utf-8")
    print(f"  [+] Updated project.pbxproj (Bundle ID -> {args.bundle_id}, build -> 129, extensions detached)")

    # 6. Switch Rivulet scheme LaunchAction from Debug to Release
    scheme_path = repo / "Rivulet.xcodeproj/xcshareddata/xcschemes/Rivulet.xcscheme"
    if scheme_path.exists():
        scheme = scheme_path.read_text(encoding="utf-8")
        scheme_updated = re.sub(
            r'(<LaunchAction\s+buildConfiguration = )"Debug"',
            r'\1"Release"',
            scheme,
            count=1,
        )
        if scheme_updated != scheme:
            scheme_path.write_text(scheme_updated, encoding="utf-8")
            print("  [+] Switched Rivulet scheme Run configuration to Release")


if __name__ == "__main__":
    main()
