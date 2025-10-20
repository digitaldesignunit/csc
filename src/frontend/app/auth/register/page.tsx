"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRouter } from "next/navigation";
import BackgroundMesh from "@/components/components/BackgroundMesh";

export default function RegisterPage() {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [focusedField, setFocusedField] = useState<string | null>(null);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    // Client-side validation
    if (!username.trim()) {
      setError("Username is required.");
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
    if (password.length < 6) {
      setError("Password must be at least 6 characters long.");
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
      }),
    });

    const data = await res.json();
    if (!res.ok) {
      setError(data.error || "Registration failed. Please try again.");
    } else {
      router.push("/auth/verification-pending");
    }
  }

  return (
    
      <div className="relative flex min-h-[70vh] md:min-h-[88vh] items-start sm:items-center justify-center p-4 pt-8 sm:pt-4">
      {/* Background Mesh */}
      <BackgroundMesh
        className="absolute inset-0 -z-10"
        opacity={0.08}
        rotationSpeed={0.15}
        intensity={0.2}
      />
      <Card className="w-full max-w-md bg-card/75">
          <CardHeader>
            <CardTitle>Register</CardTitle>
          </CardHeader>
          <CardContent>
            {error && <p className="text-sm text-destructive mb-4">{error}</p>}
            
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="gap-1 flex flex-col">
                <Label htmlFor="username">Username</Label>
                <Input 
                  id="username" 
                  value={username} 
                  onChange={(e) => setUsername(e.target.value)} 
                  onFocus={() => setFocusedField('username')}
                  onBlur={() => setFocusedField(null)}
                  placeholder={focusedField === 'username' ? '' : 're-usevelt'}
                  className="backdrop-blur placeholder:opacity-40"
                />
              </div>

              <div className="gap-1 flex flex-col">
                <Label htmlFor="fullName">Full Name</Label>
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
                <Label htmlFor="email">
                  E-Mail (<span className="text-red-600">must be @*.tu-darmstadt.de!</span>)
                </Label>
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  onFocus={() => setFocusedField('email')}
                  onBlur={() => setFocusedField(null)}
                  placeholder={focusedField === 'email' ? '' : 'franklin.re-usevelt@stud.tu-darmstadt.de'}
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

              <div className="p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-md backdrop-blur">
                <p className="text-sm text-amber-800 dark:text-amber-200">
                  <strong>Security Notice:</strong> This is research and development software. 
                  While we follow security best practices and properly hash passwords, we cannot 
                  guarantee complete safety. Please use a unique password that you don&apos;t use 
                  elsewhere.
                </p>
              </div>

              <Button type="submit" className="w-full">Register</Button>
            </form>
            
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
