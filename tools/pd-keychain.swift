// pd-keychain — macOS Keychain helper with Touch ID enforcement.
//
// Build:
//   swiftc -O -o ~/.local/bin/pd-keychain tools/pd-keychain.swift
//
// Usage:
//   pd-keychain store <account>          # Reads secret from stdin, stores with Touch ID ACL
//   pd-keychain get <account>            # Returns secret (Touch ID prompt)
//   pd-keychain delete <account>         # Removes the keychain item
//   pd-keychain exists <account>         # Exit 0 if present, 1 if not
//
// Items are stored under service "performance-dudes-pd". Access requires
// biometric authentication (Touch ID) or the user's login password as
// fallback. Items are bound to this device (not synced to iCloud).

import Foundation
import Security
import LocalAuthentication

let SERVICE = "performance-dudes-pd"

func eprint(_ s: String) {
    FileHandle.standardError.write((s + "\n").data(using: .utf8)!)
}

func usage() -> Never {
    eprint("Usage: pd-keychain <store|get|delete|exists> <account>")
    exit(2)
}

func store(account: String) {
    // Read secret from stdin (single line, no echo expected — caller handles that)
    guard let secret = readLine(strippingNewline: true), !secret.isEmpty else {
        eprint("Error: empty secret on stdin")
        exit(1)
    }
    guard let data = secret.data(using: .utf8) else {
        eprint("Error: could not encode secret")
        exit(1)
    }

    var error: Unmanaged<CFError>?
    guard let accessControl = SecAccessControlCreateWithFlags(
        nil,
        kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        [.userPresence],  // Touch ID or watch or password fallback
        &error
    ) else {
        eprint("Error creating access control: \(error?.takeRetainedValue().localizedDescription ?? "unknown")")
        exit(1)
    }

    // Delete any existing item first
    let deleteQuery: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: SERVICE,
        kSecAttrAccount as String: account,
    ]
    SecItemDelete(deleteQuery as CFDictionary)

    let addQuery: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: SERVICE,
        kSecAttrAccount as String: account,
        kSecValueData as String: data,
        kSecAttrAccessControl as String: accessControl,
        kSecUseDataProtectionKeychain as String: true,
    ]

    let status = SecItemAdd(addQuery as CFDictionary, nil)
    if status != errSecSuccess {
        eprint("Error storing secret: OSStatus \(status)")
        if let msg = SecCopyErrorMessageString(status, nil) {
            eprint("  \(msg)")
        }
        exit(1)
    }
}

func get(account: String) {
    let context = LAContext()
    context.localizedReason = "Unlock your PD signing key"

    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: SERVICE,
        kSecAttrAccount as String: account,
        kSecReturnData as String: true,
        kSecMatchLimit as String: kSecMatchLimitOne,
        kSecUseAuthenticationContext as String: context,
        kSecUseDataProtectionKeychain as String: true,
    ]

    var result: AnyObject?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    if status == errSecUserCanceled || status == errSecAuthFailed {
        eprint("Authentication cancelled or failed.")
        exit(3)
    }
    if status != errSecSuccess {
        eprint("Error retrieving secret: OSStatus \(status)")
        if let msg = SecCopyErrorMessageString(status, nil) {
            eprint("  \(msg)")
        }
        exit(1)
    }

    guard let data = result as? Data, let secret = String(data: data, encoding: .utf8) else {
        eprint("Error: could not decode secret")
        exit(1)
    }

    // Write to stdout without trailing newline — caller pipes into openssl/pyhanko
    FileHandle.standardOutput.write(secret.data(using: .utf8)!)
}

func delete(account: String) {
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: SERVICE,
        kSecAttrAccount as String: account,
        kSecUseDataProtectionKeychain as String: true,
    ]
    let status = SecItemDelete(query as CFDictionary)
    if status == errSecItemNotFound {
        eprint("No item found for account '\(account)'")
        exit(1)
    }
    if status != errSecSuccess {
        eprint("Error deleting: OSStatus \(status)")
        exit(1)
    }
}

func exists(account: String) {
    // Use LAContext with interactionNotAllowed to check presence without auth prompt
    let context = LAContext()
    context.interactionNotAllowed = true

    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: SERVICE,
        kSecAttrAccount as String: account,
        kSecMatchLimit as String: kSecMatchLimitOne,
        kSecUseAuthenticationContext as String: context,
        kSecUseDataProtectionKeychain as String: true,
    ]
    let status = SecItemCopyMatching(query as CFDictionary, nil)
    // errSecInteractionNotAllowed means: exists but needs auth
    if status == errSecSuccess || status == errSecInteractionNotAllowed {
        exit(0)
    }
    exit(1)
}

let args = CommandLine.arguments
if args.count < 3 { usage() }

let action = args[1]
let account = args[2]

switch action {
case "store": store(account: account)
case "get": get(account: account)
case "delete": delete(account: account)
case "exists": exists(account: account)
default: usage()
}
