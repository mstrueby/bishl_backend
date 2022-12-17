import { Link } from "react-router-dom"
const Card = ({venue}) => {
    let {name, street, zipCode, city, _id} = venue   
    
   
    return (
    <Link to={`/venues/${_id}`}>
    <div className="shadow-lg p-5 flex flex-col bg-FarmWhite rounded-lg transition ease-in-out hover:scale-105 duration-300 font-mono">
        <div className="font-bold text-center text-lg text-FarmNavy"><span className="text-FarmLime">{name}</span></div>
        <div>{street}</div>
        <div>{zipCode} {city}</div>
    </div>
    </Link>
  )
}
export default Card