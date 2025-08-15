import NextAuth, { AuthOptions } from "next-auth"
import CredentialsProvider from "next-auth/providers/credentials"
import { MongoClient } from "mongodb"
import bcrypt from "bcryptjs"

const MONGODB_URI = process.env.MONGODB_URI!
const DB_NAME = process.env.MONGODB_DB!
const COLLECTION_NAME = process.env.MONGODB_USERCOLLECTION!

declare global {
  // Add a global variable for the Mongo client promise
  var _mongoClientPromise: Promise<MongoClient> | undefined
}

let client: MongoClient

async function getClient() {
  if (!globalThis._mongoClientPromise) {
    client = new MongoClient(MONGODB_URI)
    globalThis._mongoClientPromise = client.connect()
  }
  client = await globalThis._mongoClientPromise
  return client
}

interface User {
  id: string
  name: string
  email: string
  username: string
}

async function authorizeUser(
  credentials?: { identifier: string; password: string }
): Promise<User | null> {
  if (!credentials) return null

  const { identifier, password } = credentials
  const client = await getClient()
  const db = client.db(DB_NAME)
  const users = db.collection(COLLECTION_NAME)

  // Find by username or email
  const user = await users.findOne({
    $or: [{ username: identifier }, { email: identifier }],
    disabled: { $ne: true },
  })

  if (!user) return null

  const isValid = await bcrypt.compare(password, user.hashed_password)
  if (!isValid) return null

  return {
    id: user._id.toString(), // Convert ObjectId to string
    name: user.full_name,
    email: user.email,
    username: user.username,
  }
}

export const authOptions: AuthOptions = {
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        identifier: { label: "Email or Username", type: "text" },
        password: { label: "Password", type: "password" },
      },
      authorize: authorizeUser,
    }),
  ],
  pages: {
    signIn: "/auth/signin",
    error: "/auth/signin", // shows error messages here
  },
  session: {
    strategy: "jwt",
  },
  secret: process.env.API_SECRET,
}

const handler = NextAuth(authOptions)
export { handler as GET, handler as POST }
