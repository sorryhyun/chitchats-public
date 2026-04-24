"""PowerShell-based Windows Forms setup dialog (windowed bundled mode)."""

import secrets

_PS_SETUP_FORM = r'''
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$form = New-Object System.Windows.Forms.Form
$form.Text = "ChitChats - Setup"
$form.Size = New-Object System.Drawing.Size(420, 320)
$form.StartPosition = "CenterScreen"
$form.FormBorderStyle = "FixedDialog"
$form.MaximizeBox = $false
$form.MinimizeBox = $false
$form.TopMost = $true
$form.Font = New-Object System.Drawing.Font("Segoe UI", 9)

$y = 15

$lblTitle = New-Object System.Windows.Forms.Label
$lblTitle.Location = New-Object System.Drawing.Point(20, $y)
$lblTitle.Size = New-Object System.Drawing.Size(360, 25)
$lblTitle.Text = "Welcome! Please set up your password."
$lblTitle.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$form.Controls.Add($lblTitle)
$y += 35

$lblPass = New-Object System.Windows.Forms.Label
$lblPass.Location = New-Object System.Drawing.Point(20, $y)
$lblPass.Size = New-Object System.Drawing.Size(360, 18)
$lblPass.Text = "Password (min 4 characters):"
$form.Controls.Add($lblPass)
$y += 22

$txtPass = New-Object System.Windows.Forms.TextBox
$txtPass.Location = New-Object System.Drawing.Point(20, $y)
$txtPass.Size = New-Object System.Drawing.Size(360, 25)
$txtPass.UseSystemPasswordChar = $true
$form.Controls.Add($txtPass)
$y += 35

$lblConfirm = New-Object System.Windows.Forms.Label
$lblConfirm.Location = New-Object System.Drawing.Point(20, $y)
$lblConfirm.Size = New-Object System.Drawing.Size(360, 18)
$lblConfirm.Text = "Confirm Password:"
$form.Controls.Add($lblConfirm)
$y += 22

$txtConfirm = New-Object System.Windows.Forms.TextBox
$txtConfirm.Location = New-Object System.Drawing.Point(20, $y)
$txtConfirm.Size = New-Object System.Drawing.Size(360, 25)
$txtConfirm.UseSystemPasswordChar = $true
$form.Controls.Add($txtConfirm)
$y += 35

$lblName = New-Object System.Windows.Forms.Label
$lblName.Location = New-Object System.Drawing.Point(20, $y)
$lblName.Size = New-Object System.Drawing.Size(360, 18)
$lblName.Text = "Display Name (default: User):"
$form.Controls.Add($lblName)
$y += 22

$txtName = New-Object System.Windows.Forms.TextBox
$txtName.Location = New-Object System.Drawing.Point(20, $y)
$txtName.Size = New-Object System.Drawing.Size(360, 25)
$form.Controls.Add($txtName)
$y += 40

$lblError = New-Object System.Windows.Forms.Label
$lblError.Location = New-Object System.Drawing.Point(20, $y)
$lblError.Size = New-Object System.Drawing.Size(200, 20)
$lblError.ForeColor = [System.Drawing.Color]::Red
$form.Controls.Add($lblError)

$btnOK = New-Object System.Windows.Forms.Button
$btnOK.Location = New-Object System.Drawing.Point(220, $y)
$btnOK.Size = New-Object System.Drawing.Size(75, 28)
$btnOK.Text = "OK"
$form.Controls.Add($btnOK)

$btnCancel = New-Object System.Windows.Forms.Button
$btnCancel.Location = New-Object System.Drawing.Point(305, $y)
$btnCancel.Size = New-Object System.Drawing.Size(75, 28)
$btnCancel.Text = "Cancel"
$btnCancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$form.CancelButton = $btnCancel
$form.Controls.Add($btnCancel)

$btnOK.Add_Click({
    if ($txtPass.Text.Length -lt 4) {
        $lblError.Text = "Min 4 characters."
        return
    }
    if ($txtPass.Text -ne $txtConfirm.Text) {
        $lblError.Text = "Passwords do not match."
        return
    }
    $form.DialogResult = [System.Windows.Forms.DialogResult]::OK
    $form.Close()
})

$form.AcceptButton = $btnOK
$result = $form.ShowDialog()

if ($result -eq [System.Windows.Forms.DialogResult]::OK) {
    # Use pipe separator to avoid issues with special chars in password
    Write-Output ("OK|" + $txtPass.Text + "|" + $txtName.Text)
} else {
    Write-Output "CANCELLED"
}
'''


def run_first_time_setup_gui():
    """Run first-time setup using a GUI dialog (for windowed mode without console).

    Uses PowerShell Windows Forms to show a proper setup dialog.
    Falls back to auto-generated credentials with a MessageBox notification.

    Returns:
        dict with password_hash, jwt_secret, user_name, or None if cancelled.
    """
    import bcrypt
    import subprocess

    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", _PS_SETUP_FORM],
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        output = result.stdout.strip()
        if output.startswith("OK|"):
            # Split from the right: last field is username, everything between first and last | is password.
            # This handles passwords containing | characters.
            first_pipe = output.index("|")
            last_pipe = output.rindex("|")
            password = output[first_pipe + 1:last_pipe]
            user_name = output[last_pipe + 1:] or "User"

            salt = bcrypt.gensalt()
            password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

            return {
                "password_hash": password_hash,
                "jwt_secret": secrets.token_hex(32),
                "user_name": user_name,
            }
        return None

    except Exception as e:
        print(f"GUI setup dialog failed: {e}")
        return _auto_generate_setup()


def _auto_generate_setup():
    """Fallback: auto-generate credentials and show the password via MessageBox."""
    import bcrypt
    import random
    import string

    chars = string.ascii_letters + string.digits
    password = "".join(random.choices(chars, k=12))

    salt = bcrypt.gensalt()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            0,
            f"ChitChats has been set up with an auto-generated password:\n\n"
            f"    {password}\n\n"
            f"Please save this password. You will need it to log in.\n"
            f"To change it later, edit the .env file and run:\n"
            f"    make generate-hash",
            "ChitChats - Setup Complete",
            0x40,  # MB_ICONINFORMATION
        )
    except Exception:
        pass

    return {
        "password_hash": password_hash,
        "jwt_secret": secrets.token_hex(32),
        "user_name": "User",
    }
