class Shipcontent < Formula
  desc "Call ShipContent MCP tools from the terminal"
  homepage "https://www.shipcontent.com"
  url "https://github.com/ShipcontentApp/homebrew-tap/releases/download/v0.1.1/shipcontent-0.1.1-arm64.tar.gz"
  version "0.1.1"
  sha256 "d5aa3a0d44c85f224fa6a10d1e4c69a85268f8881bcc66b2153f7e65a4ba2d6a"

  depends_on :macos
  depends_on arch: :arm64

  resource "python" do
    url "https://github.com/astral-sh/python-build-standalone/releases/download/20261110/cpython-3.14.10%2B20261110-aarch64-apple-darwin-install_only_stripped.tar.gz"
    sha256 "f15ec3d15460dd66c2eb88639b152cd9040e7d1ece11e38bf89e8f53f0171e02"
  end

  def install
    (libexec/"runtime").install resource("python")
    python = libexec/"runtime/bin/python3.14"
    system python, "-m", "pip", "install", "--no-index",
           "--target=#{libexec}/packages", "--find-links=wheelhouse", "--require-hashes", "-r", "requirements.txt"
    libexec.install "shipcontent.py", "shipcontent_auth.py"
    (bin/"shipcontent").write <<~SH
      #!/bin/sh
      export PYTHONPATH="#{libexec}/packages"
      exec "#{libexec}/runtime/bin/python3.14" "#{libexec}/shipcontent.py" "$@"
    SH
  end

  test do
    assert_equal "shipcontent #{version}", shell_output("#{bin}/shipcontent --version").strip
    assert_match "tools", shell_output("#{bin}/shipcontent tools --help")
  end
end
