"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useRouter } from "next/navigation";

export default function RegisterPage() {
  const [username, setUsername] = useState("");
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
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
      router.push("/auth/signin");
    }
  }

  return (
    <div className="flex min-h-screen items-start sm:items-center justify-center bg-background p-4 pt-8 sm:pt-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>Register</CardTitle>
        </CardHeader>
        <CardContent>
          {error && <p className="text-sm text-destructive mb-4">{error}</p>}
          
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="username">Username</Label>
              <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} />
            </div>

            <div>
              <Label htmlFor="fullName">Full Name</Label>
              <Input id="fullName" value={fullName} onChange={(e) => setFullName(e.target.value)} />
            </div>

            <div>
              <Label htmlFor="email">
                E-Mail (<span className="text-red-600">must be @*.tu-darmstadt.de!</span>)
              </Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>

            <div>
              <Label htmlFor="password">Password</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>

            <div className="p-3 bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 rounded-md">
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
