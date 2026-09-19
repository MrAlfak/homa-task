package main

import (
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
)

func main() {
	exe, err := os.Executable()
	if err != nil {
		fail("cannot locate executable: %v", err)
	}
	root, err := filepath.Abs(filepath.Dir(exe))
	if err != nil {
		fail("cannot resolve app directory: %v", err)
	}
	if err := os.Chdir(root); err != nil {
		fail("cannot enter %s: %v", root, err)
	}

	python := filepath.Join(root, "python", "python.exe")
	if _, err := os.Stat(python); err != nil {
		fail("python\\python.exe not found next to HomaTask.exe")
	}

	if _, err := os.Stat(filepath.Join(root, ".env")); err != nil {
		fail("Create a .env file next to HomaTask.exe (copy from .env.example).")
	}

	marker := filepath.Join(root, "python", "Lib", "site-packages", "aiogram")
	if _, err := os.Stat(marker); err != nil {
		fmt.Println("First run: installing packages from bundled wheels...")
		getPip := filepath.Join(root, "get-pip.py")
		if err := run(python, getPip, "--no-warn-script-location"); err != nil {
			fail("pip bootstrap failed: %v", err)
		}
		if err := run(
			python, "-m", "pip", "install", "--no-index", "--no-warn-script-location",
			"--find-links", filepath.Join(root, "wheels"),
			"-r", filepath.Join(root, "requirements.txt"),
		); err != nil {
			fail("package install failed: %v", err)
		}
	}

	cmd := exec.Command(python, filepath.Join(root, "run.py"))
	cmd.Dir = root
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Stdin = os.Stdin
	if err := cmd.Run(); err != nil {
		fail("bot exited: %v", err)
	}
}

func run(name string, args ...string) error {
	cmd := exec.Command(name, args...)
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	return cmd.Run()
}

func fail(format string, args ...interface{}) {
	fmt.Fprintf(os.Stderr, format+"\n", args...)
	fmt.Print("Press Enter to exit...")
	_, _ = fmt.Scanln()
	os.Exit(1)
}
