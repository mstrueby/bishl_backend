import { useField } from 'formik';
import { useState, useEffect } from 'react';
import { Switch } from '@headlessui/react'


const Toggle = ({ label, ...props }) => {
    const [field, meta, helpers] = useField(props);
    const classInputDef = "block w-full rounded-md border-gray-300 shadow-sm focus:border-indigo-500 focus:ring-indigo-500 sm:text-sm"
    const classInputErr = "block w-full rounded-md border-red-300 pr-10 text-red-900 focus:border-red-500 focus:outline-none focus:ring-red-500 sm:text-sm"
    const [enabled, setEnabled] = useState(false)
    console.log("Toggle Field name: ", field.name, ", value: ", field.value)
    console.log(field)

    function doSwitch() {
        if (enabled) {
            helpers.setValue(false)
            setEnabled(false)
        } else {
            helpers.setValue(true)
            setEnabled(true)
        }
        // if (field.value == true) {
        //     setEnabled(true)
        // } else {
        //     setEnabled(false)
        // }
        console.log("useEffect value: ", field.value)
    }

    useEffect(() => {
        if (field.value == true) {
            setEnabled(true)
        } else {
            setEnabled(false)
        }
    })

    return (
        // <div>
        //     <label htmlFor={props.id || props.name}
        //         className="block text-sm font-medium text-gray-700">
        //         {label}
        //     </label>
        //     <div className="relative mt-1 rounded-md shadow-sm">
        //         <input
        //             className={classNames(
        //                 enabled ? 'bg-indigo-600' : 'bg-gray-200',
        //                 'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2'
        //                 )}
        //             {...field} {...props}
        //         />
        //         {meta.touched && meta.error ? (
        //             <p className="mt-2 text-sm text-red-600">
        //                 {meta.error}
        //             </p>
        //         ) : null}
        //     </div>
        // </div>


        <Switch
            // {...field} {...props}
            value="true"
            name={field.name}
            checked={enabled}
            onChange={doSwitch}
            className={classNames(
                enabled ? 'bg-indigo-600' : 'bg-gray-200',
                'relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2'
            )}
        >
            <span className="sr-only">Use setting</span>
            <span
                aria-hidden="true"
                className={classNames(
                    enabled ? 'translate-x-5' : 'translate-x-0',
                    'pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out'
                )}
            />
        </Switch>
    )
};

function classNames(...classes) {
    return classes.filter(Boolean).join(' ')
}

export default Toggle;
