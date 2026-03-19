#!/usr/bin/env python3
"""Generate OpenSSL key/CSR assets and bundle issued certs into PKCS#12 files."""

from __future__ import annotations

import argparse
import getpass
import shlex
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


DEFAULT_SUBJECT = {
    "C": "US",
    "ST": "NY",
    "L": "City",
    "O": "org_name",
    "OU": "org_department",
}


def run_command(command: list[str]) -> None:
    print(f"+ {shlex.join(command)}")
    try:
        subprocess.run(command, check=True)
    except FileNotFoundError:
        sys.exit("OpenSSL was not found in PATH.")
    except subprocess.CalledProcessError as exc:
        sys.exit(exc.returncode)


def build_subject(args: argparse.Namespace) -> str:
    parts = [
        f"/C={args.country}",
        f"/ST={args.state}",
        f"/L={args.locality}",
        f"/O={args.organization}",
        f"/OU={args.org_unit}",
        f"/CN={args.cn}",
    ]
    return "".join(parts)


def normalize_sans(cn: str, sans: list[str] | None) -> list[str]:
    if sans:
        values = [name.strip() for name in sans if name.strip()]
    else:
        values = [cn]

    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def san_extension(sans: list[str]) -> str:
    return ",".join(f"DNS:{name}" for name in sans)


def prompt_with_default(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    if value:
        return value
    return default or ""


def prompt_yes_no(prompt: str, default: bool = True) -> bool:
    label = "Y/n" if default else "y/N"
    while True:
        value = input(f"{prompt} [{label}]: ").strip().lower()
        if not value:
            return default
        if value in {"y", "yes"}:
            return True
        if value in {"n", "no"}:
            return False
        print("Please answer y or n.")


def prompt_sans(cn: str) -> list[str]:
    print("Enter SAN values one at a time. Press Enter on a blank line when finished.")
    print(f"The CN will be included automatically if you do not enter any SANs.")
    sans: list[str] = []
    while True:
        value = input("SAN DNS name: ").strip()
        if not value:
            break
        sans.append(value)

    normalized = normalize_sans(cn, sans if sans else None)
    print(f"Using SANs: {', '.join(normalized)}")
    return normalized


def interactive_generate() -> SimpleNamespace:
    print("Generate a new private key and CSR")
    cn = prompt_with_default("Common Name (CN)")
    if not cn:
        sys.exit("CN is required.")

    return SimpleNamespace(
        cn=cn,
        san=prompt_sans(cn),
        key_bits=int(prompt_with_default("RSA key size", "2048")),
        output_dir=Path(prompt_with_default("Output directory", ".")),
        country=prompt_with_default("Country", DEFAULT_SUBJECT["C"]),
        state=prompt_with_default("State", DEFAULT_SUBJECT["ST"]),
        locality=prompt_with_default("Locality", DEFAULT_SUBJECT["L"]),
        organization=prompt_with_default("Organization", DEFAULT_SUBJECT["O"]),
        org_unit=prompt_with_default("Org Unit", DEFAULT_SUBJECT["OU"]),
    )


def interactive_bundle() -> SimpleNamespace:
    print("Bundle an issued certificate chain into a PFX file")
    cn = prompt_with_default("Common Name (CN)")
    if not cn:
        sys.exit("CN is required.")

    use_password = prompt_yes_no("Protect the PFX with a password?", True)
    password = None
    no_password = False
    if use_password:
        first = getpass.getpass("Enter PFX export password: ")
        second = getpass.getpass("Confirm PFX export password: ")
        if first != second:
            sys.exit("Passwords did not match.")
        password = first
    else:
        no_password = True

    return SimpleNamespace(
        cn=cn,
        key=prompt_with_default("Path to private key", f"{cn}.key"),
        chain=prompt_with_default("Path to certificate chain", f"{cn.replace('.', '_')}_chain.cer"),
        output_dir=Path(prompt_with_default("Output directory", ".")),
        output_name=prompt_with_default("PFX filename", f"bundle_{cn}.pfx"),
        friendly_name=prompt_with_default("Friendly name (optional)", "") or None,
        password=password,
        no_password=no_password,
    )


def interactive_mode() -> SimpleNamespace:
    print("Certificate Tool")
    print("1. Generate a private key and CSR")
    print("2. Build a PFX from an existing key and CA-issued chain")
    choice = prompt_with_default("Choose an option", "1")
    if choice == "1":
        args = interactive_generate()
        args.func = generate_assets
        return args
    if choice == "2":
        args = interactive_bundle()
        args.func = bundle_pfx
        return args
    sys.exit("Please choose 1 or 2.")


def generate_assets(args: argparse.Namespace) -> None:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    key_path = output_dir / f"{args.cn}.key"
    csr_path = output_dir / f"{args.cn}.csr"
    sans = normalize_sans(args.cn, args.san)

    gen_key_cmd = [
        "openssl",
        "genpkey",
        "-algorithm",
        "RSA",
        "-out",
        str(key_path),
        "-pkeyopt",
        f"rsa_keygen_bits:{args.key_bits}",
    ]

    csr_cmd = [
        "openssl",
        "req",
        "-new",
        "-key",
        str(key_path),
        "-out",
        str(csr_path),
        "-subj",
        build_subject(args),
        "-addext",
        f"subjectAltName={san_extension(sans)}",
    ]

    run_command(gen_key_cmd)
    run_command(csr_cmd)

    print()
    print(f"Key created: {key_path}")
    print(f"CSR created: {csr_path}")
    print(f"SANs: {', '.join(sans)}")


def bundle_pfx(args: argparse.Namespace) -> None:
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    key_path = Path(args.key).resolve()
    chain_path = Path(args.chain).resolve()
    output_name = args.output_name or f"bundle_{args.cn}.pfx"
    pfx_path = output_dir / output_name

    if not key_path.exists():
        sys.exit(f"Key file not found: {key_path}")
    if not chain_path.exists():
        sys.exit(f"Certificate chain file not found: {chain_path}")

    export_password = args.password
    if export_password is None and not args.no_password:
        first = getpass.getpass("Enter PFX export password: ")
        second = getpass.getpass("Confirm PFX export password: ")
        if first != second:
            sys.exit("Passwords did not match.")
        export_password = first

    pkcs12_cmd = [
        "openssl",
        "pkcs12",
        "-export",
        "-inkey",
        str(key_path),
        "-in",
        str(chain_path),
        "-out",
        str(pfx_path),
    ]

    if args.friendly_name:
        pkcs12_cmd.extend(["-name", args.friendly_name])

    if args.no_password:
        pkcs12_cmd.extend(["-passout", "pass:"])
    elif export_password is not None:
        pkcs12_cmd.extend(["-passout", f"pass:{export_password}"])

    run_command(pkcs12_cmd)

    print()
    print(f"PFX created: {pfx_path}")


def add_subject_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--country", default=DEFAULT_SUBJECT["C"], help="Subject C value")
    parser.add_argument("--state", default=DEFAULT_SUBJECT["ST"], help="Subject ST value")
    parser.add_argument("--locality", default=DEFAULT_SUBJECT["L"], help="Subject L value")
    parser.add_argument(
        "--organization",
        default=DEFAULT_SUBJECT["O"],
        help="Subject O value",
    )
    parser.add_argument("--org-unit", default=DEFAULT_SUBJECT["OU"], help="Subject OU value")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Automate OpenSSL key/CSR generation and PKCS#12 bundling.",
        epilog="Run without arguments to start interactive mode.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    generate_parser = subparsers.add_parser(
        "generate", help="Create a new private key and CSR for a CN."
    )
    generate_parser.add_argument("cn", help="Common Name to use for filenames and subject CN")
    generate_parser.add_argument(
        "--san",
        action="append",
        help="Add a DNS SAN entry. Repeat to add multiple values. Defaults to the CN.",
    )
    generate_parser.add_argument(
        "--key-bits",
        type=int,
        default=2048,
        help="RSA key size in bits (default: 2048)",
    )
    generate_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for generated files",
    )
    add_subject_arguments(generate_parser)
    generate_parser.set_defaults(func=generate_assets)

    bundle_parser = subparsers.add_parser(
        "bundle", help="Create a .pfx file from a key and issued certificate chain."
    )
    bundle_parser.add_argument("cn", help="Common Name used for default output naming")
    bundle_parser.add_argument("--key", required=True, help="Path to the private key file")
    bundle_parser.add_argument(
        "--chain",
        required=True,
        help="Path to the issued certificate or chain file from the CA",
    )
    bundle_parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Directory for the resulting PFX file",
    )
    bundle_parser.add_argument(
        "--output-name",
        help="Override the PFX filename (default: bundle_<CN>.pfx)",
    )
    bundle_parser.add_argument("--friendly-name", help="Optional friendly name for the PFX")
    bundle_parser.add_argument(
        "--password",
        help="PFX export password. If omitted, the script prompts securely.",
    )
    bundle_parser.add_argument(
        "--no-password",
        action="store_true",
        help="Create the PFX with an empty export password.",
    )
    bundle_parser.set_defaults(func=bundle_pfx)

    return parser


def main() -> None:
    parser = build_parser()
    if len(sys.argv) == 1:
        args = interactive_mode()
    else:
        args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
