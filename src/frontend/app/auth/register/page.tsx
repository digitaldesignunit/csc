"use client";

import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { WriteButton } from "@/components/ui/write-button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRouter } from "next/navigation";
import BackgroundMesh from "@/components/components/BackgroundMesh";
import { USERNAME_HINT, usernameProblem } from "@/lib/username";
import Help from "@/components/ui/help";
import { useRegistration } from "@/hooks/useRegistration";
import { codeFieldLabel, OPEN_DOMAINS_HINT, openDomainsHelp } from "@/lib/registration";

export default function RegisterPage() {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  // an invitation link carries ?code=... (decision 8.14)
  const searchParams = useSearchParams();
  const [code, setCode] = useState(searchParams.get("code") ?? "");
  // invite only (decision 8.172): the form shows once there is a code, from
  // the link or typed into the code field of the invitation page
  const [codeGiven, setCodeGiven] = useState(Boolean(searchParams.get("code")?.trim()));
  const { info, ready } = useRegistration();
  const inviteOnly = info?.inviteOnly === true;
  const [focusedField, setFocusedField] = useState<string | null>(null);
  const router = useRouter();

  function handleCode(e: React.FormEvent) {
    e.preventDefault();
    if (!code.trim()) {
      setError("Enter the invitation code from your invitation.");
      return;
    }
    setError("");
    setCodeGiven(true);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    // Client-side validation
    const nameProblem = usernameProblem(username);
    if (nameProblem) {
      setError(nameProblem);
      return;
    }
    if (!fullName.trim()) {
      setError("Full name is required.");
      return;
    }
    if (!email.trim()) {
      setError("Email is required.");
      return;
    }
    if (!password.trim()) {
      setError("Password is required.");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters long.");
      return;
    }

    const res = await fetch("/api/register", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: username.trim(),
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        ...(code.trim() ? { code: code.trim() } : {}),
      }),
    });

    const data = await res.json();
    if (!res.ok) {
      const detail = typeof data.detail === "string" ? data.detail : data.error;
      setError(detail || "Registration failed. Please try again.");
    } else if (code.trim()) {
      // the invitation proved the address: no verification mail
      router.push("/auth/signin");
    } else {
      router.push("/auth/verification-pending");
    }
  }

  return (
    
      <div className="relative flex min-h-[80vh] md:min-h-[90vh] items-start sm:items-center justify-center p-4 pt-8 sm:pt-4">
      {/* Background Mesh */}
      <BackgroundMesh
        className="absolute inset-0 -z-10"
        opacity={0.08}
        rotationSpeed={0.15}
        intensity={0.2}
        scale={1.0}
      />
      <Card className="w-full max-w-md bg-card/75">
          <CardHeader>
            <CardTitle>Register</CardTitle>
          </CardHeader>
          <CardContent>
            {error && <p className="text-sm text-destructive mb-4">{error}</p>}

            {!ready ? (
              <p className="text-sm text-muted-foreground">Loading...</p>
            ) : inviteOnly && !codeGiven ? (
              <form onSubmit={handleCode} className="space-y-4">
                <p className="text-sm">
                  Registration is by invitation only. To get an invitation, ask a moderator of the
                  dataset you want to join.
                </p>
                <div className="gap-1 flex flex-col">
                  <Label htmlFor="code">I have an invitation code</Label>
                  <Input
                    id="code"
                    value={code}
                    onChange={(e) => setCode(e.target.value.toUpperCase())}
                    autoCapitalize="characters"
                    autoCorrect="off"
                    spellCheck={false}
                    className="backdrop-blur font-mono"
                  />
                </div>
                <WriteButton type="submit" className="w-full">Continue</WriteButton>
              </form>
            ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="gap-1 flex flex-col">
                <Label htmlFor="email">E-mail</Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onFocus={() => setFocusedField('email')}
                  onBlur={() => setFocusedField(null)}
                  placeholder={focusedField === 'email' ? '' : 'name@example.org'}
                  className="backdrop-blur placeholder:opacity-40"
                />
                <p className="text-xs text-muted-foreground">
                  {code || inviteOnly ? (
                    "Use the address the invitation was sent to."
                  ) : info ? (
                    <>
                      {OPEN_DOMAINS_HINT}{" "}
                      <span className="inline-block align-middle">
                        <Help label="Open registration domains" text={openDomainsHelp(info.openDomains)} />
                      </span>
                    </>
                  ) : (
                    "An address outside the open domains needs an invitation code."
                  )}
                </p>
              </div>

              <div className="gap-1 flex flex-col">
                <Label htmlFor="code">{codeFieldLabel(info, Boolean(code))}</Label>
                <Input
                  id="code"
                  value={code}
                  onChange={(e) => setCode(e.target.value.toUpperCase())}
                  autoCapitalize="characters"
                  autoCorrect="off"
                  spellCheck={false}
                  className="backdrop-blur font-mono"
                />
              </div>

              <div className="gap-1 flex flex-col">
                <Label htmlFor="username">Username</Label>
                <Input 
                  id="username" 
                  value={username} 
                  onChange={(e) => setUsername(e.target.value.toLowerCase())}
                  onFocus={() => setFocusedField('username')}
                  onBlur={() => setFocusedField(null)}
                  placeholder={focusedField === 'username' ? '' : 're-usevelt'}
                  autoCapitalize="none"
                  autoCorrect="off"
                  spellCheck={false}
                  className="backdrop-blur placeholder:opacity-40"
                />
                <p className="text-xs text-muted-foreground">
                  {USERNAME_HINT}
                </p>
              </div>

              <div className="gap-1 flex flex-col">
                <Label htmlFor="fullName">Full name</Label>
                <Input 
                  id="fullName" 
                  value={fullName} 
                  onChange={(e) => setFullName(e.target.value)} 
                  onFocus={() => setFocusedField('fullName')}
                  onBlur={() => setFocusedField(null)}
                  placeholder={focusedField === 'fullName' ? '' : 'Franklin Re-Usevelt'}
                  className="backdrop-blur placeholder:opacity-40"
                />
              </div>

              <div className="gap-1 flex flex-col">
                <Label htmlFor="password">Password</Label>
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onFocus={() => setFocusedField('password')}
                  onBlur={() => setFocusedField(null)}
                  placeholder={focusedField === 'password' ? '' : 'Enter a secure password'}
                  className="backdrop-blur placeholder:opacity-40"
                />
              </div>

              <p className="text-xs text-muted-foreground">
                Research software: use a password you use nowhere else.
              </p>

              <p className="text-xs text-muted-foreground">
                What the site does with your data is in the{' '}
                <a href="/privacy" target="_blank" rel="noreferrer" className="font-medium text-primary underline underline-offset-2">
                  privacy notice
                </a>
                .
              </p>

              <WriteButton type="submit" className="w-full">Register</WriteButton>
            </form>
            )}
            
            <div className="mt-4 text-center text-sm text-muted-foreground">
              Already have an account?{' '}
              <a 
                href="/auth/signin" 
                className="text-primary hover:underline font-medium"
              >
                Sign in here
              </a>
            </div>
          </CardContent>
        </Card>
      </div>
  );
}
