"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import {
  onAuthStateChanged,
  signInWithEmailAndPassword,
  createUserWithEmailAndPassword,
  signInWithPopup,
  GoogleAuthProvider,
  sendPasswordResetEmail,
  sendEmailVerification,
  signOut as firebaseSignOut,
  type User,
} from "firebase/auth";
import { getFirebaseAuth } from "@/lib/firebase";

interface AuthContextValue {
  user: User | null;
  loading: boolean;
  getIdToken: () => Promise<string | null>;
  signInWithEmail: (email: string, password: string) => Promise<void>;
  registerWithEmail: (email: string, password: string) => Promise<void>;
  signInWithGoogle: () => Promise<void>;
  resetPassword: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    // Only runs in the browser — safe to touch Firebase here.
    const unsubscribe = onAuthStateChanged(getFirebaseAuth(), (u) => {
      setUser(u);
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const getIdToken = async () => {
    const auth = getFirebaseAuth();
    if (!auth.currentUser) return null;
    return auth.currentUser.getIdToken();
  };

  const signInWithEmail = async (email: string, password: string) => {
    await signInWithEmailAndPassword(getFirebaseAuth(), email, password);
  };

  const registerWithEmail = async (email: string, password: string) => {
    const cred = await createUserWithEmailAndPassword(getFirebaseAuth(), email, password);
    await sendEmailVerification(cred.user);
  };

  const signInWithGoogle = async () => {
    await signInWithPopup(getFirebaseAuth(), new GoogleAuthProvider());
  };

  const resetPassword = async (email: string) => {
    await sendPasswordResetEmail(getFirebaseAuth(), email);
  };

  const signOut = async () => {
    await firebaseSignOut(getFirebaseAuth());
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        getIdToken,
        signInWithEmail,
        registerWithEmail,
        signInWithGoogle,
        resetPassword,
        signOut,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
