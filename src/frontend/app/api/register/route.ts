// app/api/auth/register/route.ts
import { NextResponse } from "next/server";
import bcrypt from "bcryptjs";
import clientPromise from "@/lib/mongodb"; // your MongoDB connection helper

// Define your User type based on your existing MongoDB schema
interface User {
  _id: string; // GUID
  username: string;
  full_name: string;
  email: string;
  hashed_password: string;
  disabled: boolean;
}

export async function POST(req: Request) {
  try {
    const { username, full_name, email, password } = await req.json();

    // Require TU Darmstadt email
    if (!email.match(/^[^@]+@([^.]+\.)*tu-darmstadt\.de$/)) {
      return NextResponse.json(
        { message: "Only TU Darmstadt email addresses are allowed" },
        { status: 400 }
      );
    }

    const client = await clientPromise;
    const db = client.db("csc");
    const users = db.collection<User>("users"); // typed collection

    // Check if user with this email or username already exists
    const existingUser = await users.findOne({
      $or: [{ email }, { username }]
    })
    if (existingUser) {
      return NextResponse.json(
        { message: "User with this email already exists" },
        { status: 400 }
      );
    }

    // Hash password
    const hashedPassword = await bcrypt.hash(password, 10);

    // Insert new user
    await users.insertOne({
      _id: crypto.randomUUID(), // store GUID
      username,
      full_name,
      email,
      hashed_password: hashedPassword,
      disabled: false
    });

    return NextResponse.json({ message: "User registered successfully" });
  } catch (error) {
    console.error(error);
    return NextResponse.json(
      { message: "Internal server error" },
      { status: 500 }
    );
  }
}
