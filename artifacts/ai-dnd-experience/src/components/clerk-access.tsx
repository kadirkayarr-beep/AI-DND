import {
  ClerkLoaded,
  ClerkLoading,
  Show,
  SignInButton,
  SignUpButton,
  UserButton,
} from "@clerk/react";
import type { ReactNode } from "react";
import ClerkApiSession from "@/components/clerk-api-session";

export default function ClerkAccess({ children }: { children: ReactNode }) {
  return (
    <>
      <ClerkLoading>
        <main
          style={{
            minHeight: "100vh",
            display: "grid",
            placeItems: "center",
            background: "#100e0c",
            color: "#d9bd8b",
            fontFamily: "Georgia, serif",
          }}
        >
          <p>Kapılar açılıyor...</p>
        </main>
      </ClerkLoading>
      <ClerkLoaded>
        <Show when="signed-out">
          <main
            style={{
              minHeight: "100vh",
              display: "grid",
              placeItems: "center",
              padding: "24px",
              background:
                "radial-gradient(ellipse at center, #292016 0%, #110e0c 75%)",
              color: "#e7d5b6",
              fontFamily: "Georgia, serif",
            }}
          >
            <section
              style={{
                width: "100%",
                maxWidth: 520,
                padding: "clamp(28px, 6vw, 64px)",
                textAlign: "center",
                border: "1px solid #67513a",
                background: "#17120e",
                boxShadow: "0 24px 90px #0008",
              }}
            >
              <p
                style={{
                  fontSize: 11,
                  letterSpacing: "0.22em",
                  textTransform: "uppercase",
                  color: "#b39461",
                }}
              >
                Forgotten Realms
              </p>
              <h1
                style={{
                  fontSize: "clamp(32px, 6vw, 54px)",
                  fontWeight: 400,
                  lineHeight: 1.1,
                  margin: "18px 0 20px",
                }}
              >
                Macera seni bekliyor.
              </h1>
              <p
                style={{
                  color: "#b7a58d",
                  fontSize: 17,
                  lineHeight: 1.7,
                  marginBottom: 34,
                }}
              >
                Yolculuğuna devam etmek veya yeni bir hikâyeye başlamak için
                hesabına giriş yap.
              </p>
              <div
                style={{
                  display: "flex",
                  justifyContent: "center",
                  flexWrap: "wrap",
                  gap: 12,
                }}
              >
                <SignInButton mode="modal">
                  <button
                    type="button"
                    style={{
                      padding: "14px 26px",
                      border: "1px solid #ba8861",
                      background: "#8c5138",
                      color: "#fff4e7",
                      cursor: "pointer",
                      fontSize: 14,
                    }}
                  >
                    Giriş Yap
                  </button>
                </SignInButton>
                <SignUpButton mode="modal">
                  <button
                    type="button"
                    style={{
                      padding: "14px 26px",
                      border: "1px solid #806647",
                      background: "transparent",
                      color: "#e7d5b6",
                      cursor: "pointer",
                      fontSize: 14,
                    }}
                  >
                    Hesap Oluştur
                  </button>
                </SignUpButton>
              </div>
            </section>
          </main>
        </Show>
        <Show when="signed-in">
          <ClerkApiSession>{children}</ClerkApiSession>
          <div
            aria-label="Oyuncu hesabı"
            style={{
              position: "fixed",
              bottom: 18,
              right: 18,
              zIndex: 60,
              display: "flex",
              alignItems: "center",
              gap: 10,
              border: "1px solid #695039",
              background: "#19130fee",
              padding: "8px 12px",
              color: "#d9bd8b",
              fontSize: 12,
            }}
          >
            <span>Hesabım</span>
            <UserButton />
          </div>
        </Show>
      </ClerkLoaded>
    </>
  );
}
