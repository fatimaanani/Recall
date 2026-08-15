import "./GenderAvatar.css";
import femaleAvatarImg from "../assets/avatars/femaleAvatar.png";
import maleAvatarImg from "../assets/avatars/maleAvatar.png";

// Gender -> avatar image, unmapped values render an empty circle
const AVATAR_IMAGES = {
  female: femaleAvatarImg,
  male: maleAvatarImg,
};

export default function GenderAvatar({ gender, size = 96, className = "" }) {
  const src = AVATAR_IMAGES[gender];
  return (
    <span className={`gender-avatar ${className}`} style={{ width: size, height: size }}>
      {src && <img src={src} alt="" width={size} height={size} />}
    </span>
  );
}
