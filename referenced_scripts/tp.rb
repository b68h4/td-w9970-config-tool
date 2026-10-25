#!/usr/bin/env ruby

require 'openssl'

infile = ARGV[0]
content = File.read(infile)

mode = infile.end_with?('.bin') ? :decrypt : :encrypt

# Configure the cipher with what we know about the TP-Link encryption
cipher = OpenSSL::Cipher::DES.new(:ECB)
cipher.key = ["478DA50BF9E3D2CF"].pack("H*")
cipher.padding = 0

case mode
when :decrypt
  cipher.decrypt
  plaintext = cipher.update(content) + cipher.final

  # First 16 bytes are checksum of content
  reported_checksum = plaintext[0...16]
  plaintext = plaintext[16..-1]

  # Trim empty bytes used to pad out the plaintext to be multiple of 8
  plaintext = plaintext[0...-1] while plaintext.end_with?("\x0")
  checksum = OpenSSL::Digest::MD5.digest(plaintext)

  if reported_checksum != checksum
    $stderr.puts "Checksums do not match"
    $stderr.puts "reported: " << reported_checksum.bytes.map { |b| b.to_s(16) }.join
    $stderr.puts "actual:   " << checksum.bytes.map { |b| b.to_s(16) }.join
  end

  File.write(infile.sub('.bin', '.cfg'), plaintext)
when :encrypt
  # The body is prefixed with the 16 byte md5 checksum of the contents
  checksum = OpenSSL::Digest::MD5.digest(content)
  body = checksum + content

  # The body needs to be padded out with zero bytes until the byte
  # length is a multiple of 8.
  remaining = 8 - (body.length % 8)
  pad = remaining == 8 ? '' : ("\x0" * remaining)

  # Set the cipher to encryption mode and perform the action
  cipher.encrypt
  ciphertext = cipher.update(body + pad) + cipher.final
  File.write(infile.sub('.cfg', '.bin'), ciphertext)
end
