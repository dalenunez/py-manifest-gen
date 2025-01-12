#!/usr/bin/env python3

import os
import json
from collections import defaultdict

def main():
    # 1. Get KANIKO_ARTIFACTS_DIR from environment or default
    KANIKO_ARTIFACTS_DIR = os.environ.get("KANIKO_ARTIFACTS_DIR", "artifacts/kaniko-build")

    # (Optional) Print the directory structure for logging
    print(f"Traversing directory: {KANIKO_ARTIFACTS_DIR}")
    for root, dirs, files in os.walk(KANIKO_ARTIFACTS_DIR):
        level = root.replace(KANIKO_ARTIFACTS_DIR, "").count(os.sep)
        indent = " " * (4 * level)
        print(f"{indent}{os.path.basename(root)}/")
        subindent = " " * (4 * (level + 1))
        for f in files:
            print(f"{subindent}{f}")

    # 2. Find and parse all valid JSON artifacts
    build_artifacts = []
    for root, dirs, files in os.walk(KANIKO_ARTIFACTS_DIR):
        for filename in files:
            if not filename.endswith(".json"):
                continue

            filepath = os.path.join(root, filename)
            # If you want to skip /tests/, uncomment below:
            # if "/tests/" in filepath:
            #     continue

            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                build_artifacts.append({"filepath": filepath, **data})
                print(f"Valid JSON found: {filepath}")
            except (json.JSONDecodeError, OSError) as e:
                print(f"Invalid JSON: {filepath} - {e}")

    if not build_artifacts:
        print("No valid JSON artifacts found. Exiting.")
        return

    # 3. Set up environment-based variables (similar to the shell script)
    CI_COMMIT_REF_PROTECTED = os.environ.get("CI_COMMIT_REF_PROTECTED", "")
    CI_COMMIT_TAG = os.environ.get("CI_COMMIT_TAG", "")
    CI_PROJECT_ID = os.environ.get("CI_PROJECT_ID", "UNKNOWN_PROJECT_ID")
    CI_COMMIT_SHORT_SHA = os.environ.get("CI_COMMIT_SHORT_SHA", "0000000")
    CI_COMMIT_REF_SLUG = os.environ.get("CI_COMMIT_REF_SLUG", "")

    # Determine TARGET_PROJECT
    if CI_COMMIT_REF_PROTECTED == "true" or CI_COMMIT_TAG:
        TARGET_PROJECT = "release"
    else:
        TARGET_PROJECT = "prerelease"

    # Determine TAGS (a comma-separated string)
    TAGS = os.environ.get("TAGS", CI_COMMIT_SHORT_SHA)
    if CI_COMMIT_REF_SLUG:
        TAGS += f",{CI_COMMIT_REF_SLUG}"
    if CI_COMMIT_TAG:
        TAGS += f",{CI_COMMIT_TAG}"
    tags_list = [tag.strip() for tag in TAGS.split(",") if tag.strip()]

    print(f"TAGS: {TAGS}")

    # 4. Group artifacts by dockerfiledirname. Each group = one container
    #    { "tests/kaniko/images/container1": [artifact1, artifact2, ...],
    #      "main": [artifact3, ...], etc. }
    grouped_by_dir = defaultdict(list)
    for artifact in build_artifacts:
        # Fallback if no 'dockerfiledirname' is present
        dirname = artifact.get("dockerfiledirname", "unknown_directory")
        grouped_by_dir[dirname].append(artifact)

    # 5. For each dockerfiledirname, generate a separate manifest_<dirname>.yaml
    for dirname, artifacts in grouped_by_dir.items():
        # Clean up the dirname if needed to avoid weird filename chars
        # e.g. 'tests/kaniko/images/container1' -> 'tests_kaniko_images_container1'
        safe_dirname = dirname.replace("/", "_").replace("\\", "_")

        # Check which architectures we have in this group
        has_amd64 = any(a.get("arch") == "amd64" for a in artifacts)
        has_arm64 = any(a.get("arch") == "arm64" for a in artifacts)

        # If your build supports more arches (e.g., s390x, ppc64le), handle them similarly.

        # For demonstration, pick the first artifact's platform to fill in. 
        # If you have multiple platforms, you can handle them in a loop or
        # create multiple sub-entries. Below is a minimal example:
        amd64_artifact = next((a for a in artifacts if a.get("arch") == "amd64"), {})
        arm64_artifact = next((a for a in artifacts if a.get("arch") == "arm64"), {})

        # Create a distinct manifest file for this dirname
        manifest_filename = f"manifest_{safe_dirname}.yaml"
        with open(manifest_filename, "w") as yf:
            # First part
            yf.write(f"image: test.location.com/{TARGET_PROJECT}/builds/{CI_PROJECT_ID}/{dirname}/merged:{CI_COMMIT_SHORT_SHA}\n")
            yf.write("tags:\n")
            for t in tags_list:
                yf.write(f'  - "{t}"\n')

            yf.write("manifests:\n")

            if has_amd64:
                yf.write(f"  - image: test.location.com/{TARGET_PROJECT}/builds/{CI_PROJECT_ID}/{dirname}/merged:{CI_COMMIT_SHORT_SHA}\n")
                yf.write("    platform:\n")
                yf.write("      architecture: amd64\n")
                yf.write(f"      os: {amd64_artifact.get('platform', 'linux')}\n")

            if has_arm64:
                yf.write(f"  - image: test.location.com/{TARGET_PROJECT}/builds/{CI_PROJECT_ID}/{dirname}/merged:{CI_COMMIT_SHORT_SHA}\n")
                yf.write("    platform:\n")
                yf.write("      architecture: arm64\n")
                yf.write(f"      os: {arm64_artifact.get('platform', 'linux')}\n")

        print(f"Generated {manifest_filename} for {dirname}")

if __name__ == "__main__":
    main()
